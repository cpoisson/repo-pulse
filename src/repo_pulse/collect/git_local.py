"""Local git history: commits with per-file numstat."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _git(clone: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(clone), *args], capture_output=True, text=True, check=True).stdout


def default_ref(clone: Path) -> str:
    """Read upstream state without touching the user's working tree."""
    for ref in ("origin/main", "origin/master", "HEAD"):
        if subprocess.run(["git", "-C", str(clone), "rev-parse", "--verify", "-q", ref], capture_output=True).returncode == 0:
            return ref
    return "HEAD"


def commits(clone: Path, since_days: int = 400, ref: str | None = None) -> list[dict]:
    ref = ref or default_ref(clone)
    fmt = "--format=\x1e%H\x1f%an\x1f%ae\x1f%aI\x1f%s"
    out = _git(clone, "log", ref, "--no-merges", "--numstat", f"--since={since_days}.days", fmt)
    result = []
    for block in out.split("\x1e")[1:]:
        head, *lines = block.strip("\n").split("\n")
        sha, name, email, date, subject = head.split("\x1f")
        files = []
        for ln in lines:
            parts = ln.split("\t")
            if len(parts) == 3:
                a, d, p = parts
                files.append({"path": p, "add": int(a) if a.isdigit() else 0, "del": int(d) if d.isdigit() else 0})
        result.append({"sha": sha, "author": name, "email": email, "date": date, "subject": subject, "files": files})
    return result


def generated_files(clone: Path, ref: str | None = None) -> dict:
    """Files that declare themselves generated (the "Code generated ... DO NOT EDIT" convention and similar headers),
    plus `linguist-generated` patterns from .gitattributes; their lines are not anyone's work."""
    ref = ref or default_ref(clone)
    r = subprocess.run(["git", "-C", str(clone), "grep", "-l", "-i", "-E", r"generated.*do not edit|^.{0,4}@generated", ref],
                       capture_output=True, text=True)
    paths = sorted({ln.split(":", 1)[1] for ln in r.stdout.splitlines() if ":" in ln})
    patterns = [ln.split()[0] for ln in _show(clone, ref, ".gitattributes").splitlines()
                if ln.strip() and not ln.startswith("#") and re.search(r"linguist-generated(=true)?(\s|$)", ln)]
    return {"paths": paths, "patterns": patterns}


def changelog_entries(clone: Path, path: str, since_days: int = 400, ref: str | None = None) -> dict[str, list[str]]:
    """{sha: [section, ...]} from changelog fragments each commit adds under `path`: `## Fixed`-style headings inside
    the fragment (keep-a-changelog sections), else the type in a towncrier file name (123.bugfix.md)."""
    ref = ref or default_ref(clone)
    out = _git(clone, "log", ref, "--no-merges", "-p", "--format=\x1e%H", f"--since={since_days}.days", "--", path)
    result: dict[str, list[str]] = {}
    for block in out.split("\x1e")[1:]:
        sha, _, diff = block.partition("\n")
        sections: list[str] = []
        for ln in diff.splitlines():
            if ln.startswith("+++ b/"):
                parts = ln[6:].rsplit("/", 1)[-1].split(".")
                typ = parts[-2] if parts[-1] in ("md", "rst", "txt") and len(parts) >= 3 else parts[-1] if len(parts) == 2 else None
                if typ and not typ.isdigit() and typ.lower() not in ("md", "rst", "txt"):
                    sections.append(typ.lower())
            elif m := re.match(r"\+#{2,3}\s+([A-Za-z]+)", ln):
                sections.append(m.group(1).lower())
        if sections:
            result[sha.strip()] = sorted(set(sections))
    return result


def _show(clone: Path, ref: str, path: str) -> str:
    r = subprocess.run(["git", "-C", str(clone), "show", f"{ref}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def tree(clone: Path, ref: str | None = None, registry_path: str | None = None) -> dict:
    """Source/test file inventory with line counts at the upstream ref."""
    ref = ref or default_ref(clone)
    files = [f for f in _git(clone, "ls-tree", "-r", "--name-only", ref).split("\n") if f.endswith(".py")]
    inv = [{"path": f, "loc": _show(clone, ref, f).count("\n")} for f in files]
    lock = _show(clone, ref, "uv.lock")
    return {
        "ref": ref,
        "py_files": inv,
        "pyproject": _show(clone, ref, "pyproject.toml"),
        "uv_lock_packages": _lock_versions(lock) if lock else {},
        "backend_registry": _show(clone, ref, registry_path) if registry_path else "",
        "head": _git(clone, "rev-parse", "--short", ref).strip(),
    }


def star_history_from_svg(clone: Path, svg_rel: str, created_at: str) -> dict | None:
    """Fallback when the stargazers API is unavailable: decode the repo's own star-history SVG
    (x axis: repo creation -> chart commit date; y axis: 0 -> top gridline label). Approximate."""
    import re
    from datetime import datetime

    ref = default_ref(clone)
    svg = _show(clone, ref, svg_rel)
    if not svg:
        return None
    path = re.search(r'<path d="(M[^"]+)"', svg)
    grid = [(float(y), t) for y, t in re.findall(r'<text x="60" y="([\d.]+)"[^>]*class="lbl">([^<]+)<', svg)]
    if not path or len(grid) < 2:
        return None

    def val(t: str) -> float:
        t = t.replace(",", "")
        return float(t[:-1]) * 1000 if t.endswith("k") else float(t)

    (y0, t0), (y1, t1) = grid[0], grid[-1]
    y_px0, y_px1 = y0 - 4, y1 - 4  # labels are drawn 4px under their gridline
    total = re.search(r'class="total">([\d,]+) stars', svg)
    chart_date = subprocess.run(["git", "-C", str(clone), "log", ref, "-1", "--format=%cI", "--", svg_rel],
                                capture_output=True, text=True).stdout.strip()
    t_start = datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
    t_end = datetime.fromisoformat(chart_date).timestamp()
    pts = []
    for x, y in re.findall(r"[ML]([\d.]+),([\d.]+)", path.group(1)):
        if pts and float(x) < pts[-1][0]:
            break  # area paths close back along the baseline
        pts.append((float(x), float(y)))
    while len(pts) > 2 and pts[-1][0] == pts[-2][0] and pts[-1][1] > pts[-2][1]:
        pts.pop()  # drop the vertical drop to the baseline
    x_min, x_max = pts[0][0], max(p[0] for p in pts)
    series = []
    for x, y in pts:
        ts = t_start + (x - x_min) / (x_max - x_min) * (t_end - t_start)
        stars = val(t0) + (y - y_px0) / (y_px1 - y_px0) * (val(t1) - val(t0))
        series.append([datetime.fromtimestamp(ts).date().isoformat(), round(stars)])
    return {"source": f"{svg_rel} @ {chart_date[:10]}", "total_at_chart": int(total.group(1).replace(",", "")) if total else None,
            "chart_date": chart_date[:10], "series": series}


def _lock_versions(lock_text: str) -> dict[str, str]:
    """name -> highest locked version (uv.lock can hold several per platform)."""
    import tomllib

    out: dict[str, list] = {}
    for p in tomllib.loads(lock_text).get("package", []):
        out.setdefault(p["name"], []).append(p.get("version", ""))
    return {n: max(v, key=lambda x: tuple(int(t) if t.isdigit() else 0 for t in x.split("."))) for n, v in out.items()}
