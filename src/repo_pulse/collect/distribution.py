"""Download counts from the channels a project actually ships through (besides PyPI, see pypi.py).

Daily history: npm (api.npmjs.org, up to 18 months), crates.io (last 90 days).
Totals only: Docker Hub pulls and GitHub release asset downloads; window deltas come from the
edition snapshots in data/history (see collect._snapshot).
"""
from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta

import requests

UA = {"User-Agent": "repo-pulse (https://github.com/cpoisson/repo-pulse)"}
# Release assets that are fetched alongside a binary, not instead of one.
AUX_ASSET_SUFFIXES = (".sha256", ".sha512", ".sha1", ".md5", ".sig", ".asc", ".pem", ".minisig", ".intoto.jsonl",
                      ".sbom", ".spdx", ".spdx.json", ".cdx.json", "checksums.txt", "sha256sums", "sha256sums.txt")


def is_binary_asset(name: str) -> bool:
    return not name.lower().endswith(AUX_ASSET_SUFFIXES)


def npm_downloads(pkg: str, days: int) -> dict[str, int]:
    """{date: downloads}; the range endpoint caps one request at 18 months."""
    end = date.today()
    start = end - timedelta(days=min(days, 540))
    r = requests.get(f"https://api.npmjs.org/downloads/range/{start}:{end}/{pkg}", headers=UA, timeout=30)
    r.raise_for_status()
    return {d["day"]: d["downloads"] for d in r.json().get("downloads", [])}


def crates_downloads(crate: str) -> dict[str, int]:
    """{date: downloads} over the last 90 days (all versions, including those folded into extra_downloads)."""
    r = requests.get(f"https://crates.io/api/v1/crates/{crate}/downloads", headers=UA, timeout=30)
    r.raise_for_status()
    data, out = r.json(), {}
    for row in data.get("version_downloads", []) + (data.get("meta") or {}).get("extra_downloads", []):
        out[row["date"]] = out.get(row["date"], 0) + row["downloads"]
    return out


def docker_pulls(repo: str) -> int | None:
    """Total pulls of a Docker Hub repository (namespace/name); no history is published."""
    r = requests.get(f"https://hub.docker.com/v2/repositories/{repo.lower()}/", headers=UA, timeout=30)
    return r.json().get("pull_count") if r.ok else None


def github_release_assets(owner: str, name: str, max_pages: int = 10) -> list[dict]:
    """Every release with per-asset download counts (cumulative since upload)."""
    out = []
    for page in range(1, max_pages + 1):
        r = subprocess.run(["gh", "api", f"repos/{owner}/{name}/releases?per_page=100&page={page}"], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"gh releases failed: {r.stderr.strip()[:300]}")
        batch = json.loads(r.stdout)
        out += [{"tag": rel["tag_name"], "publishedAt": rel.get("published_at"), "prerelease": rel.get("prerelease", False),
                 "assets": [{"name": a["name"], "downloads": a["download_count"]} for a in rel.get("assets", [])]}
                for rel in batch]
        if len(batch) < 100:
            break
    return out


def release_download_total(releases: list[dict]) -> int:
    return sum(a["downloads"] for rel in releases for a in rel["assets"] if is_binary_asset(a["name"]))
