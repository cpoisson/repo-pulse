"""Adoption & reach: stars, forks, downloads per distribution channel, HF Hub, releases."""
from __future__ import annotations

import json
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..collect.distribution import is_binary_asset
from ..config import CHANNELS, Config
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


def _daily(by_day: dict[str, int], w: Windows) -> tuple[int | None, int | None, str, list]:
    """Window sums over a {date: downloads} series, a coverage note, and complete weeks for the chart."""
    if not by_day:
        return None, None, "", []
    first_day, last_day = min(by_day), max(by_day)
    day = lambda d: datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
    covered = lambda win: day(first_day) <= win[0] + timedelta(days=1)
    total = lambda win: sum(v for d, v in by_day.items() if within(day(d), win))
    wkly = defaultdict(int)
    for d, v in by_day.items():
        t = datetime.fromisoformat(d)
        wkly[(t - timedelta(days=t.weekday())).date().isoformat()] += v
    complete = lambda wk: (datetime.fromisoformat(wk) + timedelta(days=6)).date().isoformat() <= last_day
    weeks = sorted([k_, v] for k_, v in wkly.items() if complete(k_) and k_ >= w.prior[0].date().isoformat())
    note = "" if covered(w.prior) else f"prior window only partly covered (data starts {first_day})"
    return total(w.cur) if covered(w.cur) else None, total(w.prior) if covered(w.prior) else None, note, weeks


def _snapshot_window(rows: list[dict], value, w: Windows) -> tuple[int | None, int | None, str | None]:
    """Exact window deltas of a cumulative counter from edition snapshots; None until one predates the window."""
    pts = [(datetime.fromisoformat(r["date"]).replace(tzinfo=timezone.utc), v) for r in rows if (v := value(r)) is not None]
    at = lambda when: next((v for d, v in reversed(pts) if d <= when), None)
    now, cur0, prior0 = at(w.as_of), at(w.cur[0]), at(w.prior[0])
    first = pts[0][0].date().isoformat() if pts else None
    return (now - cur0 if now is not None and cur0 is not None else None,
            cur0 - prior0 if cur0 is not None and prior0 is not None else None, first)


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
        hist = {"source": f"{cfg.forge_name} stargazers API", "exact": True, "series": series}
    else:
        hist = raw.get("star_history") or {}
    series = hist.get("series", [])
    s_cur_start = _stars_at(series, w.cur[0])
    s_prior_start = _stars_at(series, w.prior[0])
    new_cur = round(stars_now - s_cur_start) if stars_now is not None and s_cur_start is not None else None
    new_prior = round(s_cur_start - s_prior_start) if s_cur_start is not None and s_prior_start is not None else None
    star_note = "" if hist.get("exact") else (f"approx. — derived from {hist['source']}" if hist else "no star history available")
    k += [
        kpi("stars_total", f"{cfg.forge_name} stars (total)", stars_now, source=f"{cfg.forge_name} API"),
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

    snap = Path("data/history") / f"{cfg.slug}.jsonl"
    rows = [json.loads(l) for l in snap.read_text().splitlines()] if snap.exists() else []
    download_keys, sources, weekly_charts = [], [], []
    for d in cfg.distribution:
        typ = d["type"]
        if typ in ("pypi", "npm", "crates") and any(x["type"] == typ for x in cfg.distribution[:cfg.distribution.index(d)]):
            continue  # one KPI per daily channel type; extra packages are summed below
        if typ not in ("pypi", "npm", "crates"):
            continue  # totals-only channels are handled below
        names = [x["name"] for x in cfg.distribution if x["type"] == typ]
        if typ == "pypi":
            by_day = {r["date"]: r["downloads"] for r in (raw.get("pypi") or {}).get("overall", []) if r.get("category") == "without_mirrors"}
            key, label, src = "pypi_downloads", "PyPI downloads (no mirrors)", "pypistats.org"
        elif typ in ("npm", "crates"):
            by_day = defaultdict(int)
            for series in (raw.get(typ) or {}).values():
                for day_, v in series.items():
                    by_day[day_] += v
            key, label, src = f"{typ}_downloads", f"{CHANNELS[typ]} downloads", "api.npmjs.org" if typ == "npm" else "crates.io"
        cur, prior, note, weeks = _daily(dict(by_day), w)
        if len(names) > 1:
            note = "; ".join(x for x in (f"sum of {', '.join(names)}", note) if x)
        k.append(kpi(key, label, cur, prior, note=note or ("" if by_day else "no download data collected"), source=src))
        download_keys.append(key); sources.append(src)
        if weeks:
            weekly_charts.append({"name": label, "points": weeks})
    if cfg.pypi:  # kept for the "who downloads" breakdown on the adoption slide
        for kind in ("system", "python_minor"):
            agg = defaultdict(int)
            for r in (raw.get("pypi") or {}).get(kind, []):
                if within(datetime.fromisoformat(r["date"]).replace(tzinfo=timezone.utc), w.cur):
                    agg[r["category"]] += r["downloads"]
            charts[f"pypi_{kind}"] = sorted(agg.items(), key=lambda x: -x[1])
    if weekly_charts:
        charts["downloads_weekly"] = weekly_charts[0]

    docker_repos = [d["name"] for d in cfg.distribution if d["type"] == "docker"]
    if docker_repos:
        pulls = raw.get("docker") or {}
        total = sum(v for v in pulls.values() if v) if pulls else None
        cur, prior, first = _snapshot_window(rows, lambda r: sum((r.get("docker_pulls") or {}).values()) if r.get("docker_pulls") else None, w)
        k += [kpi("docker_pulls", "Docker Hub pulls in window", cur, prior, source="hub.docker.com",
                  note=f"{', '.join(docker_repos)}; window counts start once a snapshot predates the window (first: {first})" if cur is None else ", ".join(docker_repos)),
              kpi("docker_pulls_total", "Docker Hub pulls (all time)", total, source="hub.docker.com", note=", ".join(f"{r_} {v:,}" for r_, v in pulls.items() if v))]
        download_keys += ["docker_pulls", "docker_pulls_total"]; sources.append("Docker Hub")
    if any(d["type"] == "github_releases" for d in cfg.distribution) and raw.get("release_assets") is not None:
        rel_assets = raw["release_assets"]
        per_release = [[r_["tag"], (r_["publishedAt"] or "")[:10], sum(a["downloads"] for a in r_["assets"] if is_binary_asset(a["name"]))]
                       for r_ in rel_assets if r_["publishedAt"] and not r_["prerelease"]]
        cur, prior, first = _snapshot_window(rows, lambda r: r.get("release_downloads"), w)
        if cur is not None:
            k.append(kpi("release_downloads", "Release binary downloads in window", cur, prior, source="GitHub release assets",
                         note="checksums and signatures excluded"))
        else:
            in_win = [n_ for _, d_, n_ in per_release if within(datetime.fromisoformat(d_).replace(tzinfo=timezone.utc), w.cur)]
            k.append(kpi("release_downloads", "Release binary downloads", sum(in_win) if in_win else 0,
                         source="GitHub release assets",
                         note=f"to date, from the {len(in_win)} releases published in this window; checksums and signatures excluded; "
                              f"exact window counts once a snapshot predates the window (first: {first})"))
        ctx["release_downloads"] = per_release[:8]
        download_keys.append("release_downloads"); sources.append("GitHub release assets")
    ctx["download_keys"] = download_keys
    ctx["distribution_sources"] = sources

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
        kpi("releases", f"Releases ({cfg.forge_name}{' or PyPI' if cfg.pypi else ''})", sum(within(ts(r["publishedAt"]), w.cur) for r in rels), sum(within(ts(r["publishedAt"]), w.prior) for r in rels)),
        kpi("days_since_release", "Days since last release", round(days(last, w.as_of)) if last else None, rule=cfg.thresholds.get("days_since_release")),
        kpi("dependents", "GitHub dependents (Used by)", (raw.get("dependents") or {}).get("count"), note="best-effort scrape" if cfg.forge == "github" else "GitHub only; not collected"),
    ]
    ctx["releases"] = [[r["tagName"], r["publishedAt"][:10]] for r in rels]
    ctx["snapshots"] = rows
    return k, ctx, charts
