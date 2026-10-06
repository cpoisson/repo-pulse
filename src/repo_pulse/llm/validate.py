"""Grounding check: every number in a narrative claim must be derivable from the metrics it cites.

A claim is {"text": str, "metrics": [kpi keys]}. Claims citing unknown keys, or containing numbers that match
no representation of the cited metrics, are dropped and logged. Nothing the LLM computes reaches the deck unchecked.
"""
from __future__ import annotations

import re

NUM = re.compile(r"(?<![\w#.])[-+−]?\d[\d,]*(?:\.\d+)?(?![\w])")
ALWAYS_OK = {0, 1, 2}  # trivially safe; constants such as "7 days" are allowed via the cited metric's own label/note


def _reprs(m: dict) -> set[float]:
    out: set[float] = set()
    v, p, d = m.get("value"), m.get("prior"), m.get("delta")
    for x in (v, p, d):
        if isinstance(x, (int, float)):
            out |= {x, abs(x)}
            if m.get("unit") == "ratio" or (isinstance(x, float) and abs(x) <= 1.5):
                out |= {x * 100, abs(x) * 100}
    if isinstance(v, (int, float)) and isinstance(p, (int, float)) and p:
        ch = (v - p) / abs(p) * 100
        out |= {ch, abs(ch), v / p, abs(v / p)}
        if v:
            out |= {p / v, abs(p / v)}
    for txt in (m.get("label", ""), m.get("note", ""), m.get("unit", "")):
        out |= {float(n.replace(",", "")) for n in NUM.findall(txt)}
    return out


def _matches(n: float, reps: set[float]) -> bool:
    for r in reps:
        tol = max(0.06 * abs(r), 0.6 if abs(r) >= 1 else 0.06)
        if abs(n - r) <= tol:
            return True
    return False


def check_claim(claim: dict, kpis: dict, extra_numbers: set[float] = frozenset(), window_days: int | None = None) -> tuple[bool, str]:
    keys = claim.get("metrics") or []
    unknown = [k for k in keys if k not in kpis]
    if unknown:
        return False, f"unknown metric keys {unknown}"
    reps = set(extra_numbers)
    for k in keys:
        reps |= _reprs(kpis[k])
    # Facts (text, issue/why) are number-checked. Goals and plans (outcome, actions, target) are proposals, not claims,
    # so they are not number-checked, but the item must still cite metrics.
    text = " ".join(claim.get(f, "") for f in ("text", "why", "issue"))
    for raw in NUM.findall(text):
        n = float(raw.replace(",", "").replace("−", "-"))
        if abs(n) in ALWAYS_OK or n == window_days or 1990 <= n <= 2100 and raw.isdigit():
            continue
        if not _matches(n, reps) and not _matches(-n, reps):
            return False, f"number {raw} not supported by {keys or 'no cited metrics'}"
    return True, ""


def validate(narr: dict, metrics: dict) -> tuple[dict, list[str]]:
    kpis = metrics["kpis"]
    extra = {float(x) for x in _context_numbers(metrics)}
    dropped: list[str] = []

    def keep(c, where):
        ok, why = check_claim(c, kpis, extra, metrics.get("window_days"))
        if not ok:
            dropped.append(f"{where}: {why} — “{c.get('text', '')[:120]}”")
        return ok

    out = dict(narr)
    out["findings"] = [c for c in narr.get("findings", []) if keep(c, "finding")]
    recs = [c for c in narr.get("recommendations", []) if keep(c, "recommendation")]
    out["recommendations"] = sorted(recs, key=lambda c: c.get("priority", 99))
    slides = {}
    for sid, s in (narr.get("slides") or {}).items():
        s = dict(s)
        if s.get("so_what") and not keep({"text": s["so_what"], "metrics": s.get("metrics", [])}, f"slide {sid}"):
            s["so_what"] = ""
        slides[sid] = s
    out["slides"] = slides
    nuts = {}
    for sid, n in (narr.get("nutshells") or {}).items():
        nuts[sid] = n if keep(n, f"nutshell {sid}") else {"text": "", "metrics": []}
    out["nutshells"] = nuts
    if narr.get("headline") and not keep({"text": narr["headline"], "metrics": narr.get("headline_metrics", [])}, "headline"):
        out["headline"] = ""
    out["dropped"] = dropped
    return out, dropped


def _context_numbers(metrics: dict) -> set[float]:
    """Issue/PR numbers and other identifiers that legitimately appear in text (e.g. '#627')."""
    nums: set[float] = set()
    ctx = metrics.get("context", {})
    for row in ctx.get("flow", {}).get("unanswered_open_issues", []) + ctx.get("flow", {}).get("stale_prs", []):
        nums.add(float(row[0]))
    for r in ctx.get("themes", {}).get("pain_map", []):
        nums |= {float(e[0]) for e in r.get("examples", [])}
        nums |= {float(r["cur"]), float(r["prior"]), float(r["open"])}
    for d in ctx.get("code", {}).get("dependencies", []):
        for v in (d.get("pinned") or "", d.get("latest") or ""):
            nums |= {float(x) for x in re.findall(r"\d+(?:\.\d+)?", v)}
    return nums
