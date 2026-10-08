"""Codebase & quality: churn hotspots, bus factor, CI, test coverage proxy, dependency risk, backend matrix."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from fnmatch import fnmatch
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


GENERATED_GLOBS = ("vendor/*", "*/vendor/*", "node_modules/*", "*.min.js", "*.min.css", "*_pb2.py", "*_pb2_grpc.py",
                   "*.pb.go", "*.pb.gw.go", "*_pb.js", "*_pb.d.ts", "*.snap")
LOCKFILES = {"uv.lock", "poetry.lock", "pdm.lock", "Pipfile.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
             "Cargo.lock", "go.sum", "go.mod", "Gemfile.lock", "composer.lock", "deps.bzl", "MODULE.bazel.lock"}
BUILD_DIRS = {".github", ".gitlab", ".buildkite", ".circleci", ".devcontainer", ".husky"}
BUILD_FILES = {"Makefile", "BUILD", "BUILD.bazel", "WORKSPACE", "WORKSPACE.bazel", "MODULE.bazel", "CMakeLists.txt",
               ".gitlab-ci.yml", ".pre-commit-config.yaml", "tox.ini", "noxfile.py", "setup.cfg", "setup.py", "pyproject.toml",
               "package.json", "Cargo.toml", ".bazelrc", ".bazelversion", ".gitignore", ".dockerignore", "Jenkinsfile", "justfile"}
TEST_DIRS = {"test", "tests", "testing", "__tests__", "testdata", "testutil", "e2e", "fixtures", "spec", "specs"}
TEST_FILE = re.compile(r"(^test_.*\.py$|_test\.(go|py)$|\.(test|spec)\.[cm]?[jt]sx?$|^conftest\.py$)")
DOC_DIRS = {"docs", "doc", "changelog", "changelog.d", "newsfragments", "changes", ".changeset"}
DOC_FILE = re.compile(r"(\.(md|mdx|rst|adoc)$|^(readme|changelog|license|notice|authors|contributing|security)\b)", re.I)
# Changelog sections and towncrier types -> what the change means for users.
FUNCTIONAL = {"added": "feature", "add": "feature", "feature": "feature", "features": "feature", "new": "feature",
              "fixed": "fix", "fix": "fix", "bugfix": "fix", "bugfixes": "fix", "bug": "fix", "security": "fix",
              "changed": "change", "change": "change", "improvement": "change", "improvements": "change",
              "enhancement": "change", "performance": "change", "perf": "change",
              "removed": "removal", "removal": "removal", "deprecated": "removal", "deprecation": "removal", "breaking": "removal",
              "ignored": "internal", "misc": "internal", "trivial": "internal", "internal": "internal", "chore": "internal",
              "doc": "docs", "docs": "docs", "documentation": "docs"}


def new_path(p: str) -> str:
    """numstat writes renames as `a/{old => new}/b` or `old => new`; keep the new path."""
    if " => " not in p:
        return p
    if m := re.match(r"(.*)\{(.*) => (.*)\}(.*)", p):
        return re.sub("/+", "/", m[1] + m[3] + m[4])
    return p.split(" => ")[1]


def path_kind(path: str, overrides: dict[str, str] = {}, generated: frozenset | set = frozenset(), gen_globs: tuple = ()) -> str:
    for pat, kind in overrides.items():
        if path == pat or path.startswith(pat.rstrip("/") + "/") or fnmatch(path, pat):
            return kind
    if path in generated or any(fnmatch(path, g) for g in GENERATED_GLOBS + tuple(gen_globs)):
        return "generated"
    p = PurePosixPath(path)
    dirs = set(p.parts[:-1])
    if p.name in LOCKFILES or p.name.endswith(".lock") or re.match(r"requirements.*\.txt$", p.name):
        return "deps"
    if dirs & BUILD_DIRS or p.name in BUILD_FILES or p.name.startswith("Dockerfile") or p.suffix in (".bzl", ".bazel", ".mk", ".cmake"):
        return "build"
    if dirs & TEST_DIRS or TEST_FILE.search(p.name):
        return "tests"
    if dirs & DOC_DIRS or DOC_FILE.search(p.name):
        return "docs"
    return "code"


def work(lines: int) -> float:
    """Effort credited for changing `lines` lines in one commit: grows with size, but a 1,000-line commit counts about
    twice a 30-line one rather than 30 times, so bulk or mechanical changes don't drown out the rest."""
    return math.log2(1 + lines)


PR_FUNCTIONAL_ORDER = ("feature", "fix", "change", "internal")   # a PR logged under several sections takes the first


def pr_type(pr: dict, kind, sections: list[str] | None) -> str:
    """feature / fix / change / internal from the changelog fragment of a merged PR; no_code when every file it touches
    is tests, docs, build, deps or generated; else untyped (open, closed, unlogged, or no file list)."""
    kinds = {kind(f["path"]) for f in pr.get("files") or []}
    if kinds and not kinds & {"code"}:
        return "no_code"
    funcs = {{"removal": "change"}.get(FUNCTIONAL.get(s, "internal"), FUNCTIONAL.get(s, "internal")) for s in sections or []}
    funcs = {"internal" if f in ("docs", "other") else f for f in funcs}
    return next((f for f in PR_FUNCTIONAL_ORDER if f in funcs), "untyped")


def compute(cfg: Config, raw: dict, w: Windows) -> tuple[list[dict], dict, dict]:
    k, ctx, charts = [], {}, {}
    commits = [c for c in raw.get("commits", []) if not cfg.is_bot(c["author"])]
    gen = raw.get("generated") or {}
    generated, gen_globs = frozenset(gen.get("paths", [])), tuple(gen.get("patterns", []))
    kind = lambda p: path_kind(p, cfg.path_kinds, generated, gen_globs)
    changelog = raw.get("changelog") or {}

    def churn(win):
        mod_lines, mod_commits, files = Counter(), Counter(), Counter()
        mod_work: dict[str, Counter] = defaultdict(Counter)
        authors, code_work = Counter(), Counter()
        author_mix: dict[str, Counter] = defaultdict(Counter)
        functional: dict[str, Counter] = defaultdict(Counter)
        for c in commits:
            if not within(ts(c["date"]), win):
                continue
            authors[c["author"]] += 1
            by_kind, by_mod_code, touched = Counter(), Counter(), set()
            for f in c["files"]:
                path, n = new_path(f["path"]), f["add"] + f["del"]
                kd = kind(path)
                # changelog fragments are bookkeeping read for the functional mix below, not work of their own
                if kd in ("generated", "deps") or cfg.changelog_fragments and path.startswith(cfg.changelog_fragments):
                    continue
                by_kind[kd] += n
                m = cfg.module_for(path)
                mod_lines[m] += n
                files[path] += n
                touched.add(m)
                if kd == "code":
                    by_mod_code[m] += n
            for m in touched:
                mod_commits[m] += 1
            for m, n in by_mod_code.items():
                mod_work[m][c["author"]] += work(n)
            for kd, n in by_kind.items():
                author_mix[c["author"]][kd] += work(n)
            code_work[c["author"]] += work(by_kind["code"])
            for sec in {FUNCTIONAL.get(s, "other") for s in changelog.get(c["sha"], [])}:
                functional[c["author"]][sec] += 1
            if c["sha"] in changelog:
                functional[c["author"]]["_logged"] += 1
        return mod_lines, mod_commits, files, mod_work, authors, +code_work, author_mix, functional

    # PRs opened in the window, typed; a merged PR's changelog comes from its squash commit, found by the "(#N)" suffix
    by_pr = {int(m[1]): changelog.get(c["sha"]) for c in commits if (m := re.search(r"\(#(\d+)\)\s*$", c["subject"]))}
    pr_kind = lambda p: path_kind(p, {cfg.changelog_fragments: "docs"} | cfg.path_kinds if cfg.changelog_fragments else cfg.path_kinds,
                                  generated, gen_globs)
    pr_types: dict[str, Counter] = defaultdict(Counter)
    for pr in raw.get("pulls", []):
        if within(ts(pr["createdAt"]), w.cur) and not cfg.is_bot(pr["author"]):
            secs = by_pr.get(pr["number"]) if pr.get("mergedAt") else None
            t = pr_type(pr, pr_kind, secs)
            if t == "untyped" and changelog:   # with a changelog, say why a code PR has no type yet
                t = "unlogged" if pr.get("mergedAt") else "closed" if pr.get("closedAt") else "open"
            pr_types[pr["author"]][t] += 1
    charts["pr_types"] = {a: dict(c) for a, c in pr_types.items()}

    ml, mc, files, mwork, authors, cwork, mix, func = churn(w.cur)
    mlp, _, _, _, authors_p, cwork_p, _, func_p = churn(w.prior)
    charts["module_churn"] = [[m, ml[m], mlp.get(m, 0), mc[m]] for m, _ in ml.most_common()]
    charts["hotspot_files"] = files.most_common(12)
    charts["commit_authors"] = authors.most_common(8)
    top = sorted(mix, key=lambda a: -sum(mix[a].values()))[:8]
    team = sum(sum(m.values()) for m in mix.values()) or 1   # shares of the whole team's weighted work, all kinds
    charts["work_by_author"] = [[a, {kd: round(v / team, 4) for kd, v in mix[a].items()}, authors[a], dict(func.get(a, {}))] for a in top]
    ctx["module_bus_factor"] = {m: bus_factor(a) for m, a in mwork.items()}
    ctx["module_top_author_share"] = {m: ratio(a.most_common(1)[0][1], sum(a.values())) for m, a in mwork.items() if a}
    module_code_commits = Counter(m for c in commits if within(ts(c["date"]), w.cur)
                                  for m in {cfg.module_for(new_path(f["path"])) for f in c["files"] if kind(new_path(f["path"])) == "code"})
    share = lambda cw: ratio(cw.most_common(1)[0][1], sum(cw.values())) if cw else None
    work_note = "commits weighted by log2(1 + code lines); tests, docs, build, lockfiles and generated files excluded"
    k += [
        kpi("commits", "Commits (non-merge, humans)", sum(authors.values()), sum(authors_p.values()), source="local git"),
        kpi("commit_authors", "Commit authors", len(authors), len(authors_p)),
        kpi("bus_factor", "Bus factor (50% of code work)", bus_factor(cwork), bus_factor(cwork_p),
            rule=cfg.thresholds.get("bus_factor"), note=work_note),
        kpi("code_concentration", "Code concentration (top author's share)", share(cwork), share(cwork_p),
            "ratio", lower_is_better=True, note=work_note),
        kpi("modules_single_owner", "Single-owner modules (>80% of code work)",
            sum(1 for m, s in ctx["module_top_author_share"].items() if s and s > 0.8 and module_code_commits[m] >= 3),
            lower_is_better=True, note="modules with ≥3 code commits in window"),
    ]
    if changelog:
        tot = lambda f, key: sum(c.get(key, 0) for c in f.values())
        n_cur = sum(authors.values())
        note = f"from changelog fragments in {cfg.changelog_fragments}; a commit can be in several categories"
        k += [
            kpi("changes_features", "Commits adding a feature (changelog)", tot(func, "feature"), tot(func_p, "feature"), note=note),
            kpi("changes_fixes", "Commits fixing a bug (changelog)", tot(func, "fix"), tot(func_p, "fix"), note=note),
            kpi("changelog_coverage", "Commits with a changelog fragment", ratio(tot(func, "_logged"), n_cur),
                ratio(tot(func_p, "_logged"), sum(authors_p.values())), "ratio"),
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
