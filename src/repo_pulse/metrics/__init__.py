"""Deterministic metrics: raw data -> metrics.json. The LLM never computes numbers."""
from __future__ import annotations

from ..config import Config
from . import adoption, code, flow, themes
from .util import Windows

# Whether "up" is good. Everything else with lower_is_better=False and no threshold is shown neutral.
GOOD_UP = {"issues_closed", "response_within_7d", "prs_merged", "pr_merge_rate", "external_pr_merge_rate", "external_pr_share",
           "external_merged_share", "pr_contributors", "new_contributors", "issue_reporters", "stars_new", "stars_growth_rate",
           "forks_new", "forks_active", "pypi_downloads", "hf_spaces_new", "releases", "dependents", "commit_authors", "bus_factor",
           "ci_pass_rate_main", "ci_pass_rate_pr", "test_loc_ratio", "backends_with_tests", "classifier_coverage"}

FAMILIES = {"flow": flow, "adoption": adoption, "code": code, "themes": themes}


def compute(cfg: Config, raw: dict, as_of: str) -> dict:
    w = Windows.of(as_of, cfg.window_days)
    out = {
        "repo": cfg.repo, "forge": cfg.forge_name, "title": cfg.title, "as_of": as_of, "window_days": cfg.window_days,
        "windows": {"cur": [w.cur[0].date().isoformat(), as_of], "prior": [w.prior[0].date().isoformat(), w.cur[0].date().isoformat()]},
        "kpis": {}, "context": {}, "charts": {}, "families": {},
    }
    for fam, mod in FAMILIES.items():
        kpis, ctx, charts = mod.compute(cfg, raw, w)
        for item in kpis:
            item["family"] = fam
            item["direction"] = "down" if item["lower_is_better"] else "up" if item["key"] in GOOD_UP else "neutral"
            out["kpis"][item["key"]] = item
        out["families"][fam] = [x["key"] for x in kpis]
        out["context"][fam] = ctx
        out["charts"].update(charts)
    return out
