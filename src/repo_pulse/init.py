"""`repo-pulse init owner/name`: clone the repo (history limited to the analysis span) and write a starter config.

Everything inferable is inferred (module map, test keywords, PyPI package, critical deps). The issue theme taxonomy
is left empty on purpose: it should be proposed from the repo's own issues (see the skill), not guessed.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import requests
import yaml

from .config import default_clone

CODE_EXT = (".py", ".js", ".ts", ".tsx", ".rs", ".go", ".java", ".kt", ".swift", ".c", ".cc", ".cpp", ".h", ".rb", ".cs")
SKIP_DIRS = {".github", "docs", "doc", "examples", "scripts", "archive", "assets", "benchmarks", "demo", "tests", "test", "notebooks"}

DEFAULTS = {
    "window_days": 90,
    "maintainers": [],
    "bots": ["dependabot", "github-actions", "Copilot", "copilot-pull-request-reviewer"],
    "issue_types": {
        "bug": "Something is broken, crashes, errors, or behaves incorrectly.",
        "enhancement": "A request for a new feature, model, backend, or improvement.",
        "question": "A usage question, help request, or discussion without a concrete defect.",
    },
    "themes": {},
    "thresholds": {
        "median_first_response_days": {"good": 2, "bad": 7, "lower_is_better": True},
        "median_time_to_merge_days": {"good": 3, "bad": 14, "lower_is_better": True},
        "pr_merge_rate": {"good": 0.6, "bad": 0.35},
        "external_pr_share": {"good": 0.4, "bad": 0.15},
        "stale_open_prs": {"good": 5, "bad": 20, "lower_is_better": True},
        "open_issues_over_90d": {"good": 20, "bad": 60, "lower_is_better": True},
        "ci_pass_rate_main": {"good": 0.9, "bad": 0.7},
        "bus_factor": {"good": 3, "bad": 1},
        "days_since_release": {"good": 45, "bad": 120, "lower_is_better": True},
    },
    "classifier": "local",   # local (free) | auto (best measured incl. API models) | jev (force TypeSafe Jev)
    "classifier_gate": {"min_macro_f1": 0.7, "max_ece": 0.1, "target_precision": 0.85},
}


def _run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def clone(repo: str, since_days: int, dest: Path | None = None) -> Path:
    dest = dest or default_clone(repo)
    since = (date.today() - timedelta(days=since_days)).isoformat()
    if dest.exists():
        subprocess.run(["git", "-C", str(dest), "fetch", "-q", f"--shallow-since={since}", "origin"], capture_output=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"cloning {repo} (history since {since})…", file=sys.stderr)
        url = f"https://github.com/{repo}.git"
        r = subprocess.run(["git", "clone", "-q", "--no-checkout", f"--shallow-since={since}", url, str(dest)], capture_output=True)
        if r.returncode != 0:  # quiet repo: no commit in the window makes --shallow-since fail; keep the tip instead
            shutil.rmtree(dest, ignore_errors=True)
            _run("git", "clone", "-q", "--no-checkout", "--depth=1", url, str(dest))
    return dest


def module_map(files: list[str]) -> dict[str, str]:
    """Top-level code dirs; the dominant one (e.g. src/<pkg>) is expanded into its subpackages."""
    code = [f for f in files if f.endswith(CODE_EXT)]
    top = Counter(f.split("/")[0] for f in code if "/" in f)
    mods: dict[str, str] = {}

    def expand(prefix: str, depth: int) -> None:
        inner = Counter(f[len(prefix) + 1:].split("/")[0] for f in code if f.startswith(prefix + "/") and f.count("/") > prefix.count("/") + 1)
        total = sum(1 for f in code if f.startswith(prefix + "/"))
        # src/<pkg>: one child holds nearly everything -> go one level deeper
        if depth < 2 and inner and inner.most_common(1)[0][1] > 0.8 * total:
            expand(f"{prefix}/{inner.most_common(1)[0][0]}", depth + 1)
            return
        for child, n in inner.most_common(14):
            if n >= 2 and child not in SKIP_DIRS and not child.startswith(("_", ".")):
                mods[f"{prefix}/{child}"] = child
        mods[prefix] = "core"

    if top:
        main, n = top.most_common(1)[0]
        if n > 0.6 * sum(top.values()):
            expand(main, 0)          # single dominant package (src/<pkg>, <pkg>/)
        else:                        # several side-by-side components (monorepo / multi-language)
            for d, cnt in top.most_common(12):
                if cnt < 5 or d in SKIP_DIRS or d.startswith((".", "_")):
                    continue
                kids = Counter(f.split("/")[1] for f in code if f.startswith(d + "/") and f.count("/") >= 2)
                big = [k for k, c in kids.items() if c >= 3 and k not in SKIP_DIRS]
                if len(big) >= 2 and max(kids.values()) < 0.8 * cnt:   # workspace like rust/<crate>
                    for k in big:
                        mods[f"{d}/{k}"] = k
                mods[d] = d
    for d in ("tests", "test", "docs", "examples", "scripts", "demo", ".github"):
        if any(f.startswith(d + "/") for f in files):
            mods[d] = {"test": "tests", ".github": "ci"}.get(d, d)
    for f in ("pyproject.toml", "setup.py", "package.json", "Dockerfile", "uv.lock"):
        if f in files:
            mods[f] = "packaging"
    if "README.md" in files:
        mods["README.md"] = "docs"
    # longest prefix first so specific modules win
    return dict(sorted(mods.items(), key=lambda kv: -len(kv[0])))


def python_meta(clone_dir: Path, ref: str, files: list[str], repo_name: str) -> tuple[str | None, list[str]]:
    """PyPI package + direct deps from pyproject.toml files at depth <= 2 (monorepos have several)."""
    names, deps = [], []
    for f in sorted((f for f in files if f.endswith("pyproject.toml") and f.count("/") <= 2), key=lambda f: f.count("/")):
        try:
            data = tomllib.loads(_run("git", "show", f"{ref}:{f}", cwd=clone_dir)).get("project", {})
        except Exception:
            continue
        if data.get("name"):
            names.append(data["name"])
        deps += [re.split(r"[\s<>=!~;\[]", d.strip(), maxsplit=1)[0].lower() for d in data.get("dependencies", [])]
    names.sort(key=lambda n: n.lower().replace("_", "-") != repo_name.lower())   # the repo's namesake first
    name = next((n for n in names if requests.get(f"https://pypi.org/pypi/{n}/json", timeout=20).ok), None)
    heavy = ("torch", "transformers", "tensorflow", "jax", "numpy", "mlx", "onnxruntime", "vllm", "accelerate", "datasets", "fastapi", "pydantic")
    ranked = [d for d in deps if d in heavy] + [d for d in deps if d not in heavy]
    return name, list(dict.fromkeys(ranked))[:8]


def init(repo: str, out_dir: str = "configs", window_days: int = 90) -> Path:
    owner, name = repo.split("/")
    dest = clone(repo, since_days=window_days * 2 + 60)
    ref = "origin/HEAD" if subprocess.run(["git", "-C", str(dest), "rev-parse", "-q", "--verify", "origin/HEAD"], capture_output=True).returncode == 0 else "HEAD"
    files = _run("git", "ls-tree", "-r", "--name-only", ref, cwd=dest).split("\n")
    mods = module_map(files)
    pypi, deps = python_meta(dest, ref, files, name)
    cfg = {
        "repo": repo, "title": name, "pypi": pypi, **DEFAULTS, "window_days": window_days,
        "modules": mods,
        "module_test_keywords": {m: [m.lower().replace("-", "_")] for m in sorted(set(mods.values())) if m not in ("core", "tests", "docs", "ci", "packaging", "examples", "scripts", "demo")},
        "critical_dependencies": deps,
        "known_incidents": [],
        "hf_hub_queries": [],
    }
    path = Path(out_dir) / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (f"# repo-pulse config for {repo} — generated by `repo-pulse init`; review modules and fill `themes`\n"
              "# (propose 8-13 themes from the repo's issue titles; descriptions double as classifier label text).\n"
              "# Every field is documented in configs/_template.yaml.\n")
    path.write_text(header + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=120))
    return path
