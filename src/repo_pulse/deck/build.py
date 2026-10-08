"""Assemble the self-contained deck: template + deck.js + embedded data -> out/<slug>-pulse-<as_of>.html."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import Config

HERE = Path(__file__).parent
# Scorecard slides: one per entry; each has a nutshell (narrative "nutshells"[id]) and one or more tables.
SCORECARD = [
    {"id": "flow", "title": "Community & flow", "tables": {
        "Responsiveness & backlog": ["response_within_7d", "median_first_response_days", "unanswered_open_issues",
                                     "open_issues_over_90d", "stale_open_prs"],
        "Contributions": ["external_pr_share", "new_contributors", "pr_merge_rate", "external_pr_merge_rate",
                          "median_time_to_merge_external_days", "top_merger_share"]}},
    {"id": "adoption", "title": "Adoption & reach", "tables": {
        "Reach": ["stars_new", "forks_new", "forks_active", "pypi_downloads", "npm_downloads", "crates_downloads",
                  "release_downloads", "docker_pulls", "docker_pulls_total"],
        "Releases": ["releases", "days_since_release"]}},
    {"id": "code", "title": "Codebase, quality & issue themes", "tables": {
        "Ownership & quality": ["bus_factor", "top_committer_share", "modules_single_owner", "ci_pass_rate_main", "ci_pass_rate_pr",
                                "backends_with_tests", "critical_deps_behind", "critical_deps_unbounded"],
        "Issue themes": ["bug_share", "top_theme_share", "classifier_coverage"]}},
]
# First five with data are shown on the title and summary slides.
HEADLINE_KPIS = ["stars_new", "issues_opened", "prs_merged", "response_within_7d", "bus_factor",
                 "pypi_downloads", "npm_downloads", "crates_downloads", "release_downloads", "forks_new", "open_issues_over_90d", "stale_open_prs", "pr_contributors"]


def _token_report(base: Path, narr: dict) -> dict:
    u = narr.get("usage") or {}
    bake = json.loads((base / "bakeoff.json").read_text()) if (base / "bakeoff.json").exists() else {}
    dec = bake.get("decision", {})
    models = {dec.get("types", {}).get("model"), dec.get("themes", {}).get("model")} - {None}
    api_models = [m for m in models if m == "typesafe-jev"]
    parts = [f"narrative: {u.get('input_tokens', 0)} in / {u.get('output_tokens', 0)} out tokens ({u.get('model') or narr.get('source', 'n/a')})",
             f"issue triage: {'0 tokens (local models: ' + ', '.join(sorted(models)) + ')' if models and not api_models else 'API model ' + ', '.join(api_models) if api_models else 'n/a'}"]
    return {"summary": "; ".join(parts), "narrative": u}


def _people(metrics: dict) -> dict[str, str]:
    """Map every person the deck can show to a role alias, ranked by activity: maintainers, contributors, commit authors."""
    ch, flow = metrics.get("charts", {}), metrics.get("context", {}).get("flow", {})
    maint = set(flow.get("maintainers", []))
    logins = [n for n, *_ in ch.get("mergers", []) + ch.get("pr_authors", [])]
    logins += [w.get(k) for w in flow.get("flow", {}).values() for k in ("top_author", "top_merger")] + sorted(maint)
    logins += [pr[2] for pr in flow.get("stale_prs", []) if len(pr) > 2]  # [number, title, author]
    alias, nm, nc = {}, 0, 0
    for name in logins:
        if not name or name in alias:
            continue
        if name in maint:
            alias[name] = f"maintainer {chr(65 + nm) if nm < 26 else nm + 1}"; nm += 1
        else:
            nc += 1; alias[name] = f"contributor {nc}"
    for i, (name, *_) in enumerate(ch.get("commit_authors", []), 1):  # git display names, not logins
        alias.setdefault(name, f"author {i}")
    return alias


def _anonymize(obj, alias: dict[str, str]):
    """Replace people's names with role aliases in every string of the deck data (exact values and whole words)."""
    pat = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in sorted(alias, key=len, reverse=True)) + r")(?![\w-])")
    def walk(o):
        if isinstance(o, str):
            return alias.get(o) or pat.sub(lambda m: alias[m.group(1)], o)
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        return o
    return walk(obj) if alias else obj


def build(cfg: Config, as_of: str, anonymize: bool = False, note: str | None = None, out: str | None = None) -> Path:
    base = Path("data") / cfg.slug
    metrics = json.loads((base / f"metrics-{as_of}.json").read_text())
    narr_p = base / f"narrative-{as_of}.json"
    narr = json.loads(narr_p.read_text()) if narr_p.exists() else {}
    classifier = json.loads((base / "classifier.json").read_text()) if (base / "classifier.json").exists() else {}
    bake = json.loads((base / "bakeoff.json").read_text()) if (base / "bakeoff.json").exists() else {}
    prev = sorted(p for p in base.glob("narrative-2*.json") if p.name < narr_p.name)
    prev_targets = []
    if prev:
        last = json.loads(prev[-1].read_text())
        prev_targets = [f"{r.get('text')}: {r.get('target')}" for r in last.get("recommendations", [])]
    for c in classifier.values():
        if isinstance(c, dict):
            c.pop("confusion", None)  # bulky, not needed in the deck
    data = {"metrics": metrics, "narrative": narr, "classifier": classifier, "headline_kpis": [k for k in HEADLINE_KPIS if metrics["kpis"].get(k, {}).get("value") is not None][:5], "scorecard": SCORECARD,
            "target_precision": bake.get("target_precision"), "previous_targets": prev_targets, "token_report": _token_report(base, narr)}
    if anonymize:
        data = _anonymize(data, _people(metrics))
    if note:
        data["note"] = note
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (HERE / "template.html").read_text()
    html = html.replace("__TITLE__", f"{cfg.title} pulse · {as_of}").replace("__DECKJS__", (HERE / "deck.js").read_text()).replace("__DATA__", blob)
    path = Path(out) if out else Path("out") / f"{cfg.name}-pulse-{as_of}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html)
    return path
