"""Community & flow health: inflow/closure, responsiveness, merge flow, contributors, bus factor."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from ..config import Config
from .util import Windows, days, kpi, quantile, ratio, ts, weekly, within

STALE_PR_DAYS = 30
RESPONSE_SLA_DAYS = 7


def infer_maintainers(cfg: Config, pulls: list[dict], w: Windows) -> list[str]:
    if cfg.maintainers:
        return cfg.maintainers
    since = w.as_of - timedelta(days=365)
    return sorted({p["mergedBy"] for p in pulls if p.get("mergedBy") and (ts(p["mergedAt"]) or since) >= since and not cfg.is_bot(p["mergedBy"])})


def _first_response(item: dict, responders: set[str] | None, cfg: Config, author: str | None):
    """First comment/review by someone other than the author (optionally restricted to responders)."""
    events = [*(item.get("comments") or []), *(item.get("reviews") or [])]
    times = [ts(e["at"]) for e in events
             if e["author"] and e["author"] != author and not cfg.is_bot(e["author"])
             and (responders is None or e["author"] in responders) and e["at"]]
    return min(times) if times else None


def compute(cfg: Config, raw: dict, w: Windows) -> tuple[list[dict], dict, dict]:
    issues = raw.get("issues", [])
    pulls = [p for p in raw.get("pulls", []) if not cfg.is_bot(p["author"])]
    maint = set(infer_maintainers(cfg, raw.get("pulls", []), w))
    thr = cfg.thresholds
    k: list[dict] = []
    ctx: dict = {"maintainers": sorted(maint)}
    charts: dict = {}

    def per(win):
        opened = [i for i in issues if within(ts(i["createdAt"]), win)]
        closed = [i for i in issues if within(ts(i["closedAt"]), win)]
        # maintainer response to issues opened in-window by non-maintainers, old enough to judge the SLA
        ext = [i for i in opened if i["author"] not in maint and not cfg.is_bot(i["author"])]
        resp = []
        sla_ok = sla_n = 0
        for i in ext:
            created = ts(i["createdAt"])
            r = _first_response(i, maint, cfg, i["author"])
            if r:
                resp.append(days(created, r))
            if days(created, win[1]) >= RESPONSE_SLA_DAYS:
                sla_n += 1
                sla_ok += bool(r and days(created, r) <= RESPONSE_SLA_DAYS)
        # PRs from non-maintainers
        pr_open = [p for p in pulls if within(ts(p["createdAt"]), win)]
        ext_prs = [p for p in pr_open if p["author"] not in maint]
        pr_resp = [days(ts(p["createdAt"]), r) for p in ext_prs if (r := _first_response(p, maint, cfg, p["author"]))]
        pr_closed = [p for p in pulls if within(ts(p["closedAt"]), win)]
        merged = [p for p in pr_closed if p["mergedAt"]]
        ttm = [days(ts(p["createdAt"]), ts(p["mergedAt"])) for p in merged]
        ttm_ext = [days(ts(p["createdAt"]), ts(p["mergedAt"])) for p in merged if p["author"] not in maint]
        ext_closed = [p for p in pr_closed if p["author"] not in maint]
        authors = Counter(p["author"] for p in pr_open)
        mergers = Counter(p["mergedBy"] for p in merged if p.get("mergedBy"))
        first_pr = {}
        for p in sorted(pulls, key=lambda p: p["createdAt"]):
            first_pr.setdefault(p["author"], ts(p["createdAt"]))
        new_contrib = [a for a in authors if within(first_pr[a], win) and a not in maint]
        issue_authors = {i["author"] for i in opened if i["author"] and i["author"] not in maint}
        return dict(
            opened=len(opened), closed=len(closed), net=len(opened) - len(closed),
            closed_completed=sum(1 for i in closed if i.get("stateReason") == "COMPLETED")
                if all("stateReason" in i for i in closed) else None,   # GitLab records no close reason
            resp_med=quantile(resp, 0.5), resp_p90=quantile(resp, 0.9), sla=ratio(sla_ok, sla_n), sla_n=sla_n,
            pr_opened=len(pr_open), pr_ext_opened=len(ext_prs), pr_resp_med=quantile(pr_resp, 0.5),
            merged=len(merged), closed_unmerged=len(pr_closed) - len(merged),
            merge_rate=ratio(len(merged), len(pr_closed)),
            ext_merge_rate=ratio(sum(1 for p in ext_closed if p["mergedAt"]), len(ext_closed)),
            ttm_med=quantile(ttm, 0.5), ttm_p90=quantile(ttm, 0.9), ttm_ext_med=quantile(ttm_ext, 0.5),
            ext_share=ratio(len(ext_prs), len(pr_open)),
            ext_merged_share=ratio(sum(1 for p in merged if p["author"] not in maint), len(merged)),
            contributors=len(authors), new_contributors=len(new_contrib), issue_reporters=len(issue_authors),
            top_author_share=ratio(authors.most_common(1)[0][1], sum(authors.values())) if authors else None,
            top_author=authors.most_common(1)[0][0] if authors else None,
            top_merger_share=ratio(mergers.most_common(1)[0][1], sum(mergers.values())) if mergers else None,
            top_merger=mergers.most_common(1)[0][0] if mergers else None,
        )

    c, p = per(w.cur), per(w.prior)
    ctx["flow"] = {"cur": c, "prior": p}

    # open backlog at as_of
    open_now = [i for i in issues if ts(i["createdAt"]) < w.as_of and (not i["closedAt"] or ts(i["closedAt"]) >= w.as_of)]
    ages = [days(ts(i["createdAt"]), w.as_of) for i in open_now]
    buckets = {"0-7d": 0, "7-30d": 0, "30-90d": 0, ">90d": 0}
    for a in ages:
        buckets["0-7d" if a < 7 else "7-30d" if a < 30 else "30-90d" if a < 90 else ">90d"] += 1
    unanswered = [i for i in open_now if i["author"] not in maint and not _first_response(i, maint, cfg, i["author"])]
    open_prs = [p for p in pulls if p["state"] == "OPEN"]
    stale = [p for p in open_prs if not p["isDraft"] and days(ts(p["updatedAt"]), w.as_of) > STALE_PR_DAYS]
    ctx["open_issues"] = len(open_now)
    ctx["unanswered_open_issues"] = sorted(([i["number"], i["title"]] for i in unanswered), reverse=True)[:10]
    ctx["stale_prs"] = [[p["number"], p["title"], p["author"]] for p in stale][:10]

    k += [
        kpi("issues_opened", "Issues opened", c["opened"], p["opened"], source=f"{cfg.forge_name} issues"),
        kpi("issues_closed", "Issues closed", c["closed"], p["closed"], source=f"{cfg.forge_name} issues"),
        kpi("issue_backlog_net", "Net issue backlog change", c["net"], p["net"], lower_is_better=True,
            note="opened − closed in window"),
        kpi("open_issues", "Open issues (now)", len(open_now), lower_is_better=True),
        kpi("open_issues_over_90d", "Open issues older than 90 days", buckets[">90d"], rule=thr.get("open_issues_over_90d")),
        kpi("unanswered_open_issues", "Open issues with no maintainer reply", len(unanswered), lower_is_better=True),
        kpi("median_first_response_days", "Median maintainer first response (issues)", c["resp_med"], p["resp_med"], "days",
            thr.get("median_first_response_days"), note="non-maintainer issues; responded ones only"),
        kpi("p90_first_response_days", "p90 maintainer first response (issues)", c["resp_p90"], p["resp_p90"], "days", lower_is_better=True),
        kpi("response_within_7d", "Issues answered by a maintainer within 7 days", c["sla"], p["sla"], "ratio",
            note=f"n={c['sla_n']} issues ≥7 days old"),
        kpi("median_pr_first_response_days", "Median maintainer first response (external PRs)", c["pr_resp_med"], p["pr_resp_med"], "days", lower_is_better=True),
        kpi("prs_opened", "PRs opened (humans)", c["pr_opened"], p["pr_opened"]),
        kpi("prs_merged", "PRs merged", c["merged"], p["merged"]),
        kpi("pr_merge_rate", "PR merge rate (of closed)", c["merge_rate"], p["merge_rate"], "ratio", thr.get("pr_merge_rate")),
        kpi("external_pr_merge_rate", "External PR merge rate (of closed)", c["ext_merge_rate"], p["ext_merge_rate"], "ratio"),
        kpi("median_time_to_merge_days", "Median time to merge", c["ttm_med"], p["ttm_med"], "days", thr.get("median_time_to_merge_days")),
        kpi("median_time_to_merge_external_days", "Median time to merge (external PRs)", c["ttm_ext_med"], p["ttm_ext_med"], "days", lower_is_better=True),
        kpi("stale_open_prs", f"Open PRs idle > {STALE_PR_DAYS} days", len(stale), rule=thr.get("stale_open_prs")),
        kpi("external_pr_share", "Share of PRs from outside maintainers", c["ext_share"], p["ext_share"], "ratio", thr.get("external_pr_share")),
        kpi("external_merged_share", "Share of merged PRs from outside maintainers", c["ext_merged_share"], p["ext_merged_share"], "ratio"),
        kpi("pr_contributors", "PR authors", c["contributors"], p["contributors"]),
        kpi("new_contributors", "First-time PR authors", c["new_contributors"], p["new_contributors"]),
        kpi("issue_reporters", "Distinct issue reporters", c["issue_reporters"], p["issue_reporters"]),
        kpi("top_merger_share", f"Share of merges by top merger ({c['top_merger']})" if c["top_merger"] else "Share of merges by top merger", c["top_merger_share"], p["top_merger_share"], "ratio", lower_is_better=True),
        kpi("top_author_pr_share", f"Share of PRs by top author ({c['top_author']})", c["top_author_share"], p["top_author_share"], "ratio", lower_is_better=True),
    ]

    span = (w.prior[0], w.as_of)
    charts["issue_flow"] = {
        "opened": weekly([ts(i["createdAt"]) for i in issues], *span),
        "closed": weekly([ts(i["closedAt"]) for i in issues if i["closedAt"]], *span),
    }
    charts["pr_flow"] = {
        "opened": weekly([ts(x["createdAt"]) for x in pulls], *span),
        "merged": weekly([ts(x["mergedAt"]) for x in pulls if x["mergedAt"]], *span),
    }
    charts["backlog_age"] = buckets
    charts["ttm_dist"] = sorted(round(days(ts(x["createdAt"]), ts(x["mergedAt"])), 2) for x in pulls if within(ts(x["mergedAt"]), w.cur))
    charts["resp_dist"] = sorted(
        round(days(ts(i["createdAt"]), r), 2) for i in issues
        if within(ts(i["createdAt"]), w.cur) and i["author"] not in maint and (r := _first_response(i, maint, cfg, i["author"])))
    charts["pr_authors"] = Counter(x["author"] for x in pulls if within(ts(x["createdAt"]), w.cur)).most_common(12)
    charts["mergers"] = Counter(x["mergedBy"] for x in pulls if within(ts(x["mergedAt"]), w.cur)).most_common(5)
    return k, ctx, charts
