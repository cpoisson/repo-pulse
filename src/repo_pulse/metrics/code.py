"""Codebase & quality: churn hotspots, bus factor, CI, test coverage proxy, dependency risk, backend matrix."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from ..config import Config
from .util import Windows, days, kpi, quantile, ratio, ts, within

GENERIC_TOKENS = {"stt", "tts", "llm", "language", "model", "handler", "arguments", "api", "open", "compatible", "streaming", "unified"}


def bus_factor(counts: Counter, cover: float = 0.5) -> int | None:
    total = sum(counts.values())
    if not total:
        return None
    acc = n = 0
    for _, c in counts.most_common():
        acc += c
        n += 1
        if acc >= cover * total:
            return n
    return n


def _dep_name(spec: str) -> str:
    return re.split(r"[\s<>=!~;\[]", spec.strip(), 1)[0].lower()


def compute(cfg: Config, raw: dict, w: Windows) -> tuple[list[dict], dict, dict]:
    k, ctx, charts = [], {}, {}
    commits = [c for c in raw.get("commits", []) if not cfg.is_bot(c["author"])]

    def churn(win):
        mod_lines, mod_commits, files = Counter(), Counter(), Counter()
        mod_authors: dict[str, Counter] = defaultdict(Counter)
        authors = Counter()
        for c in commits:
            if not within(ts(c["date"]), win):
                continue
            authors[c["author"]] += 1
            touched = set()
            for f in c["files"]:
                if f["path"] == "uv.lock" or f["path"].endswith(("package-lock.json", ".lock")):
                    continue
                m = cfg.module_for(f["path"])
                mod_lines[m] += f["add"] + f["del"]
                files[f["path"]] += f["add"] + f["del"]
                touched.add(m)
            for m in touched:
                mod_commits[m] += 1
                mod_authors[m][c["author"]] += 1
        return mod_lines, mod_commits, files, mod_authors, authors

    ml, mc, files, mauth, authors = churn(w.cur)
    mlp, _, _, _, authors_p = churn(w.prior)
    charts["module_churn"] = [[m, ml[m], mlp.get(m, 0), mc[m]] for m, _ in ml.most_common()]
    charts["hotspot_files"] = files.most_common(12)
    charts["commit_authors"] = authors.most_common(8)
    bf_mod = {m: bus_factor(a) for m, a in mauth.items()}
    ctx["module_bus_factor"] = bf_mod
    ctx["module_top_author_share"] = {m: ratio(a.most_common(1)[0][1], sum(a.values())) for m, a in mauth.items() if a}
    bf, bfp = bus_factor(authors), bus_factor(authors_p)
    k += [
        kpi("commits", "Commits (non-merge, humans)", sum(authors.values()), sum(authors_p.values()), source="local git"),
        kpi("commit_authors", "Commit authors", len(authors), len(authors_p)),
        kpi("bus_factor", "Bus factor (authors covering 50% of commits)", bf, bfp, rule=cfg.thresholds.get("bus_factor")),
        kpi("top_committer_share", "Top committer share of commits",
            ratio(authors.most_common(1)[0][1], sum(authors.values())) if authors else None,
            ratio(authors_p.most_common(1)[0][1], sum(authors_p.values())) if authors_p else None, "ratio", lower_is_better=True),
        kpi("modules_single_owner", "Modules where one author made >80% of commits",
            sum(1 for m, s in ctx["module_top_author_share"].items() if s and s > 0.8 and mc[m] >= 3), lower_is_better=True,
            note="modules with ≥3 commits in window"),
    ]

    runs = raw.get("ci_runs", [])
    branch = ((raw.get("repo") or {}).get("defaultBranchRef") or {}).get("name") or "main"
    push_names = Counter(r["name"] for r in runs if r["event"] == "push" and r["head_branch"] == branch)
    ci_name = cfg.ci_workflow or (push_names.most_common(1)[0][0] if push_names else "CI")
    ctx["ci_workflow"] = ci_name

    def ci(win, event, branch=None):
        rs = [r for r in runs if r["name"] == ci_name and r["event"] == event and within(ts(r["created_at"]), win)
              and (branch is None or r["head_branch"] == branch) and r["conclusion"] in ("success", "failure")]
        dur = [days(ts(r["run_started_at"]), ts(r["updated_at"])) * 1440 for r in rs if r.get("run_started_at")]
        return ratio(sum(r["conclusion"] == "success" for r in rs), len(rs)), quantile(dur, 0.5), len(rs)

    main_c, dur_c, n_c = ci(w.cur, "push", branch)
    main_p, dur_p, _ = ci(w.prior, "push", branch)
    pr_c, _, npr = ci(w.cur, "pull_request")
    pr_p, _, _ = ci(w.prior, "pull_request")
    k += [
        kpi("ci_pass_rate_main", f"CI pass rate on {branch}", main_c, main_p, "ratio", cfg.thresholds.get("ci_pass_rate_main"), note=f"n={n_c} runs", source="GitHub Actions" if cfg.forge == "github" else f"{cfg.forge_name} CI"),
        kpi("ci_pass_rate_pr", "CI pass rate on PRs", pr_c, pr_p, "ratio", note=f"n={npr} runs"),
        kpi("ci_median_minutes", f"Median CI duration ({branch})", dur_c, dur_p, "min", lower_is_better=True),
    ]
    wk = defaultdict(lambda: [0, 0])
    for r in runs:
        if r["name"] == ci_name and r["conclusion"] in ("success", "failure") and within(ts(r["created_at"]), (w.prior[0], w.as_of)):
            t = ts(r["created_at"])
            key = (t.date().toordinal() - t.weekday())
            wk[key][0] += r["conclusion"] == "success"
            wk[key][1] += 1
    from datetime import date
    last_full = w.as_of.date().toordinal() - 7
    charts["ci_weekly"] = [[date.fromordinal(o).isoformat(), ratio(s, n), n] for o, (s, n) in sorted(wk.items()) if o <= last_full]

    tree = raw.get("tree") or {}
    py = tree.get("py_files", [])
    is_test = lambda p: p.startswith(("tests/", "test/")) or "/tests/" in p or PurePosixPath(p).name.startswith("test_") or p.endswith("_test.py")
    non_src = ("docs/", "examples/", "scripts/", "archive/", "benchmarks/", "demo/", ".github/")
    tests = [f for f in py if is_test(f["path"])]
    src = [f for f in py if not is_test(f["path"]) and not f["path"].startswith(non_src)]
    test_names = " ".join(PurePosixPath(f["path"]).name.lower() for f in tests)
    mod_loc = Counter()
    for f in src:
        mod_loc[cfg.module_for(f["path"])] += f["loc"]
    coverage = {m: any(kw in test_names for kw in kws) for m, kws in cfg.module_test_keywords.items()}
    ctx["module_tested"] = coverage
    charts["module_loc"] = mod_loc.most_common()

    # backend matrix: argument classes imported by the registry
    reg = tree.get("backend_registry", "")
    pattern = (cfg.backend_registry or {}).get("pattern")
    backends = sorted(set(re.findall(pattern, reg))) if reg and pattern else []
    tested = {}
    for b in backends:
        toks = [t for t in b.split("_") if t not in GENERIC_TOKENS and len(t) > 2]
        tested[b] = any(t in test_names for t in toks) if toks else False
    ctx["backends"] = tested
    k.append(kpi("test_loc_ratio", "Test LOC / source LOC", ratio(sum(f["loc"] for f in tests), sum(f["loc"] for f in src))))
    if backends:
        label = (cfg.backend_registry or {}).get("label", "Registered backends")
        k += [kpi("backends", label, len(backends)),
              kpi("backends_with_tests", "Backends with a matching test file", ratio(sum(tested.values()), len(tested)), unit="ratio",
                  note="name-match proxy, not line coverage")]

    # dependency risk
    pyproject = tree.get("pyproject", "")
    deps_block = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", pyproject, re.S | re.M)
    specs = re.findall(r'"([^"]+)"', deps_block.group(1)) if deps_block else []
    latest = raw.get("pypi_latest", {})
    rows = []
    for dep in cfg.critical_dependencies:
        dspecs = [s for s in specs if _dep_name(s) == dep]
        pins = sorted({m for s in dspecs for m in re.findall(r"==\s*([\w.]+)", s.split(";")[0])})
        lat = latest.get(dep)
        rows.append({"dep": dep, "spec": "; ".join(dspecs) or "(not a direct dependency)", "pinned": ", ".join(pins) or None,
                     "latest": lat, "behind": bool(pins and lat and lat not in pins),
                     "pinned_somewhere": bool(pins), "unbounded": any("==" not in s.split(";")[0] and "<" not in s.split(";")[0] for s in dspecs)})
    ctx["dependencies"] = rows
    k += [
        kpi("critical_deps_behind", "Exact-pinned critical deps behind latest PyPI", sum(r["behind"] for r in rows), unit=f"of {sum(r['pinned_somewhere'] for r in rows)} pinned",
            lower_is_better=True, source="pyproject.toml vs PyPI"),
        kpi("critical_deps_unbounded", "Critical deps with no upper bound on some platform", sum(r["unbounded"] for r in rows), lower_is_better=True,
            note="exposed to breaking upstream releases"),
    ]
    ctx["known_incidents"] = cfg.known_incidents
    ctx["head"] = tree.get("head")
    return k, ctx, charts
