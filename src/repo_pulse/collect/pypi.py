"""PyPI downloads (pypistats.org, ~180 days of daily data) and latest versions."""
from __future__ import annotations

import requests

API = "https://pypistats.org/api/packages/{pkg}/{kind}"


def downloads(pkg: str) -> dict:
    out = {}
    for kind, params in [("overall", {"mirrors": "false"}), ("system", {}), ("python_minor", {})]:
        r = requests.get(API.format(pkg=pkg, kind=kind), params=params, timeout=30)
        out[kind] = r.json().get("data", []) if r.ok else []
    return out


def releases(pkg: str) -> list[list[str]]:
    """[version, first upload date] for every PyPI release (many projects ship to PyPI without GitHub Releases)."""
    r = requests.get(f"https://pypi.org/pypi/{pkg}/json", timeout=30)
    if not r.ok:
        return []
    out = []
    for v, files in r.json().get("releases", {}).items():
        times = [f.get("upload_time_iso_8601") for f in files if f.get("upload_time_iso_8601")]
        if times:
            out.append([v, min(times)])
    return sorted(out, key=lambda x: x[1])


def latest_versions(names: list[str]) -> dict[str, str | None]:
    out = {}
    for n in names:
        try:
            r = requests.get(f"https://pypi.org/pypi/{n}/json", timeout=20)
            out[n] = r.json()["info"]["version"] if r.ok else None
        except Exception:
            out[n] = None
    return out
