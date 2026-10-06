"""Adoption & reach: stars, forks, PyPI, HF Hub, releases."""
from __future__ import annotations

import json
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import Config
from .util import Windows, days, kpi, ratio, ts, weekly, within


def _stars_at(series: list[list], when: datetime) -> float | None:
    """Linear interpolation on the [date, cumulative] series; None past its end."""
    if not series:
        return None
    xs = [datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp() for d, _ in series]
    t = when.timestamp()
    if t > xs[-1] + 86400:
        return None
    i = bisect_right(xs, t)
    if i == 0:
        return 0.0
    if i >= len(xs):
        return float(series[-1][1])
    x0, x1 = xs[i - 1], xs[i]
    y0, y1 = series[i - 1][1], series[i][1]
    return y0 + (y1 - y0) * ((t - x0) / (x1 - x0) if x1 > x0 else 1)


def compute(cfg: Config, raw: dict, w: Windows) -> tuple[list[dict], dict, dict]:
    k, ctx, charts = [], {}, {}
    meta = raw.get("repo", {})
    stars_now = meta.get("stargazerCount")
    starred = sorted(t[:10] for t in (raw.get("stars") or []))
    if starred:  # exact: cumulative count per day from starredAt
        series, n = [], 0
        for d, c in sorted(Counter(starred).items()):
            n += c
            series.append([d, n])
        hist = {"source": "GitHub stargazers API", "exact": True, "series": series}
    else:
        hist = raw.get("star_history") or {}
    series = hist.get("series", [])
    s_cur_start = _stars_at(series, w.cur[0])
    s_prior_start = _stars_at(series, w.prior[0])
    new_cur = round(stars_now - s_cur_start) if stars_now is not None and s_cur_start is not None else None
    new_prior = round(s_cur_start - s_prior_start) if s_cur_start is not None and s_prior_start is not None else None
    star_note = "" if hist.get("exact") else (f"approx. — derived from {hist['source']}" if hist else "no star history available")
    k += [
        kpi("stars_total", "GitHub stars (total)", stars_now, source="GitHub API"),
        kpi("stars_new", "New stars in window", new_cur, new_prior, note=star_note),
        kpi("stars_growth_rate", "Star growth vs window start", ratio(new_cur, s_cur_start) if new_cur is not None else None,
            ratio(new_prior, s_prior_start) if new_prior is not None and s_prior_start else None, "ratio", note=star_note),
    ]
    # weekly new stars from the decoded series
    if series:
        wk, d = [], (w.prior[0] - timedelta(days=w.prior[0].weekday()))
        while d + timedelta(days=7) <= w.as_of:
            a, b = _stars_at(series, d), _stars_at(series, d + timedelta(days=7))
            if b is None and a is not None and stars_now is not None and d + timedelta(days=7) >= w.as_of - timedelta(days=1):
                b = stars_now
            wk.append([d.date().isoformat(), round(b - a) if a is not None and b is not None else None])
            d += timedelta(days=7)
        charts["stars_weekly"] = wk
        charts["stars_cumulative"] = [[d, v] for d, v in series]

    forks = raw.get("forks", [])
    fc = [f for f in forks if within(ts(f["createdAt"]), w.cur)]
    fp = [f for f in forks if within(ts(f["createdAt"]), w.prior)]
    active = [f for f in forks if within(ts(f["pushedAt"]), w.cur) and days(ts(f["createdAt"]), ts(f["pushedAt"])) > 0.04]
    k += [
        kpi("forks_total", "Forks (total)", meta.get("forkCount")),
        kpi("forks_new", "New forks", len(fc), len(fp)),
        kpi("forks_active", "Forks with own pushes in window", len(active), note="pushedAt after creation (>1h)"),
    ]
    charts["forks_weekly"] = weekly([ts(f["createdAt"]) for f in forks], w.prior[0], w.as_of)

    pypi = raw.get("pypi") or {}
    overall = [r for r in pypi.get("overall", []) if r.get("category") == "without_mirrors"]
    by_day = {r["date"]: r["downloads"] for r in overall}
    first_day = min(by_day) if by_day else None

    def dl(win):
        s = sum(v for d, v in by_day.items() if within(datetime.fromisoformat(d).replace(tzinfo=timezone.utc), win))
        covered = first_day is not None and datetime.fromisoformat(first_day).replace(tzinfo=timezone.utc) <= win[0] + timedelta(days=1)
        return s, covered

    dc, cov_c = dl(w.cur)
    dp, cov_p = dl(w.prior)
    k += [kpi("pypi_downloads", "PyPI downloads (no mirrors)", dc if by_day else None, dp if cov_p else None,
              note="" if cov_p else f"prior window only partly covered (pypistats data starts {first_day})", source="pypistats.org")]
    if by_day:
        wkly = defaultdict(int)
        for d, v in by_day.items():
            t = datetime.fromisoformat(d)
            wkly[(t - timedelta(days=t.weekday())).date().isoformat()] += v
        last_day = max(by_day)
        complete = lambda wk: (datetime.fromisoformat(wk) + timedelta(days=6)).date().isoformat() <= last_day
        charts["pypi_weekly"] = sorted([k_, v] for k_, v in wkly.items() if complete(k_))
    for kind in ("system", "python_minor"):
        agg = defaultdict(int)
        for r in pypi.get(kind, []):
            if within(datetime.fromisoformat(r["date"]).replace(tzinfo=timezone.utc), w.cur):
                agg[r["category"]] += r["downloads"]
        charts[f"pypi_{kind}"] = sorted(agg.items(), key=lambda x: -x[1])

    hub = raw.get("hfhub") or {}
    sp = hub.get("spaces", [])
    if cfg.hf_hub_queries:
        k += [kpi("hf_spaces_new", "New HF Spaces matching search terms", sum(within(ts(s.get("createdAt")), w.cur) for s in sp),
                  sum(within(ts(s.get("createdAt")), w.prior) for s in sp), note=f"search proxy: {', '.join(cfg.hf_hub_queries)}; capped at 200/query")]

    rels = [r for r in meta.get("releases", []) if r.get("publishedAt") and not r.get("isPrerelease")]
    pyrels = [{"tagName": f"PyPI {v}", "publishedAt": t} for v, t in (raw.get("pypi_releases") or [])
              if not any(x in v for x in ("a", "b", "rc", "dev"))]
    rels = sorted(rels + pyrels, key=lambda r: r["publishedAt"], reverse=True)
    last = max((ts(r["publishedAt"]) for r in rels), default=None)
    k += [
        kpi("releases", "Releases (GitHub or PyPI)", sum(within(ts(r["publishedAt"]), w.cur) for r in rels), sum(within(ts(r["publishedAt"]), w.prior) for r in rels)),
        kpi("days_since_release", "Days since last release", round(days(last, w.as_of)) if last else None, rule=cfg.thresholds.get("days_since_release")),
        kpi("dependents", "GitHub dependents (Used by)", (raw.get("dependents") or {}).get("count"), note="best-effort scrape"),
    ]
    ctx["releases"] = [[r["tagName"], r["publishedAt"][:10]] for r in rels]
    snap = Path("data/history") / f"{cfg.slug}.jsonl"
    ctx["snapshots"] = [json.loads(l) for l in snap.read_text().splitlines()] if snap.exists() else []
    return k, ctx, charts
