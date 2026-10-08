from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ..config import Config
from datetime import date, datetime, timedelta, timezone

from . import distribution, git_local, github, gitlab, hfhub, pypi
from .cache import ROOT, cached


def _snapshot(cfg: Config, as_of: str) -> None:
    """Append exact point-in-time counters so future editions get precise trends."""
    meta_path = ROOT / cfg.slug / as_of / "repo.json"
    if not meta_path.exists():
        return
    m = json.loads(meta_path.read_text())
    hist = Path("data/history") / f"{cfg.slug}.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in hist.read_text().splitlines()] if hist.exists() else []
    rows = [r for r in rows if r["date"] != as_of]
    row = {"date": as_of, "stars": m["stargazerCount"], "forks": m["forkCount"], "watchers": m["watchers"]["totalCount"],
           "open_issues": m["issues"]["totalCount"], "open_prs": m["pullRequests"]["totalCount"]}
    # download totals without published history: kept here so later editions get exact window deltas
    raw_dir = ROOT / cfg.slug / as_of
    if (raw_dir / "docker.json").exists():
        row["docker_pulls"] = json.loads((raw_dir / "docker.json").read_text())
    if (raw_dir / "release_assets.json").exists():
        row["release_downloads"] = distribution.release_download_total(json.loads((raw_dir / "release_assets.json").read_text()))
    rows.append(row)
    hist.write_text("\n".join(json.dumps(r) for r in sorted(rows, key=lambda r: r["date"])) + "\n")


def run(cfg: Config, as_of: str, refresh: bool = False) -> None:
    o, n, slug = cfg.owner, cfg.name, cfg.slug
    lookback = cfg.window_days * 2 + 30

    def step(name, fn):
        print(f"- {name}", file=sys.stderr)
        try:
            cached(slug, as_of, name, fn, refresh)
        except Exception as e:  # one failing source must not sink the edition
            print(f"  ! {name} failed: {e}", file=sys.stderr)

    since = datetime.combine(date.fromisoformat(as_of) - timedelta(days=lookback), datetime.min.time(), timezone.utc)
    if cfg.forge == "gitlab":
        pid = gitlab.project_id(cfg.repo)
        meta_fn = lambda: gitlab.repo_meta(pid)
        step("repo", meta_fn)
        step("issues", lambda: gitlab.issues(pid, since))
        step("pulls", lambda: gitlab.merge_requests(pid, since, cfg.is_bot))
        step("stars", lambda: gitlab.stars(pid))
        step("forks", lambda: gitlab.forks(pid))
        step("ci_runs", lambda: gitlab.pipelines(pid, since, cached(slug, as_of, "repo", meta_fn)["defaultBranchRef"]["name"]))
    else:
        meta_fn = lambda: github.repo_meta(o, n)
        step("repo", meta_fn)
        step("issues", lambda: github.issues(o, n))
        step("pulls", lambda: github.pulls(o, n, since))
        step("stars", lambda: github.stars(o, n, cap=40000))
        step("forks", lambda: github.forks(o, n))
        step("ci_runs", lambda: github.ci_runs(o, n, lookback))
        step("dependents", lambda: {"count": github.dependents_count(o, n)})
    if not cfg.local_clone.exists():
        from ..init import clone
        try:
            clone(cfg.repo, since_days=lookback + 30, dest=cfg.local_clone, url=cfg.web_url + ".git")
        except Exception as e:
            print(f"  ! clone failed, skipping git metrics: {e}", file=sys.stderr)
    if cfg.local_clone.exists():
        subprocess.run(["git", "-C", str(cfg.local_clone), "fetch", "-q", "origin"], capture_output=True)
        step("commits", lambda: git_local.commits(cfg.local_clone, 400))
        step("tree", lambda: git_local.tree(cfg.local_clone, registry_path=(cfg.backend_registry or {}).get("path")))
        if cfg.star_history_svg:
            meta = cached(slug, as_of, "repo", meta_fn)
            step("star_history", lambda: git_local.star_history_from_svg(cfg.local_clone, cfg.star_history_svg, meta["createdAt"]))
    channels = lambda t: [d["name"] for d in cfg.distribution if d["type"] == t]
    if channels("npm"):
        step("npm", lambda: {p: distribution.npm_downloads(p, lookback) for p in channels("npm")})
    if channels("crates"):
        step("crates", lambda: {c: distribution.crates_downloads(c) for c in channels("crates")})
    if channels("docker"):
        step("docker", lambda: {r: distribution.docker_pulls(r) for r in channels("docker")})
    if any(d["type"] == "github_releases" for d in cfg.distribution) and cfg.forge == "github":
        step("release_assets", lambda: distribution.github_release_assets(o, n))
    _snapshot(cfg, as_of)
    if cfg.pypi:
        step("pypi", lambda: pypi.downloads(cfg.pypi))
        step("pypi_latest", lambda: pypi.latest_versions(cfg.critical_dependencies))
        step("pypi_releases", lambda: pypi.releases(cfg.pypi))
    if cfg.hf_hub_queries:
        step("hfhub", lambda: hfhub.search(cfg.hf_hub_queries))
