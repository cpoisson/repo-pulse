"""Narrative: slide headlines, findings and recommendations grounded in metrics.json.

Sources, in priority order:
  1. data/<slug>/narrative-input-<as_of>.json  (hand- or agent-written; still validated)
  2. optional: one API call over a compact metrics digest (Anthropic provider, needs ANTHROPIC_API_KEY)
  3. deterministic rules (always available)
Every claim must cite metric keys; validate.py drops claims whose numbers don't match.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from ..config import Config
from .validate import validate

MODEL = "claude-opus-5-5"
SLIDE_IDS = ["flow", "responsiveness", "contributors", "adoption", "code", "quality", "themes"]

SYSTEM = """You write the analytic narrative for an executive summary deck about an open-source GitHub project.
Audience: the maintainers who steer the project. Be specific, candid and brief; no hype.
You receive a digest of pre-computed metrics (current window vs prior window). NEVER compute or invent numbers:
every number you write must appear in (or be a direct restatement of) the metrics you cite in that claim's "metrics" list
(percent change between value and prior is allowed). Claims that fail this check are automatically deleted.
Return ONLY a JSON object:
{"headline": str, "headline_metrics": [key...],
 "findings": [{"text": str, "metrics": [key...], "severity": "high|medium|low"}],            // exactly 3, most important first
 "recommendations": [  // the improvement plan: 3 to 5 items, ordered by priority (impact on project health x urgency);
                        // priority 1 must address the highest-severity finding
   {"priority": int, "text": str (clear imperative action title),
    "issue": str (the problem, with the evidence numbers; fact-checked),
    "outcome": str (what changes for the project/users when this works; no numbers needed),
    "actions": [str, ...] (2-4 concrete first steps), "owner": str, "effort": "S|M|L", "horizon": "2 weeks|this quarter|next quarter",
    "target": str (measurable target for next window, in plain words), "metrics": [key...]}],
 "nutshells": {"flow"|"adoption"|"code": {"text": str (one-sentence takeaway for that scorecard family), "metrics": [key...]}},
 "slides": {"<slide_id>": {"title": str (an assertion, not a topic), "so_what": str, "metrics": [key...]}}}
slide ids: flow, responsiveness, contributors, adoption, code, quality, themes."""


def digest(metrics: dict) -> str:
    """Compact, token-cheap view of the metrics (aggregates only, never raw issues)."""
    lines = [f"repo {metrics['repo']} as_of {metrics['as_of']} window {metrics['window_days']}d "
             f"(cur {metrics['windows']['cur']}, prior {metrics['windows']['prior']})"]
    for fam, keys in metrics["families"].items():
        lines.append(f"## {fam}")
        for k in keys:
            m = metrics["kpis"][k]
            lines.append(f"{k} | {m['label']} | {m['value']} | prior {m['prior']} | {m['unit']} | {m['status']}"
                         + (f" | {m['note']}" if m["note"] else ""))
    ctx = metrics["context"]
    lines.append("## context")
    lines.append(f"maintainers: {ctx['flow']['maintainers']}")
    lines.append(f"top PR authors (cur): {metrics['charts'].get('pr_authors', [])[:6]}")
    lines.append(f"mergers (cur): {metrics['charts'].get('mergers')}")
    lines.append(f"module churn [module, lines cur, lines prior, commits]: {metrics['charts'].get('module_churn', [])[:8]}")
    lines.append(f"module top-author share: {ctx['code'].get('module_top_author_share')}")
    lines.append(f"deps: {[(d['dep'], d['pinned'], d['latest']) for d in ctx['code'].get('dependencies', [])]}")
    lines.append(f"known incidents: {ctx['code'].get('known_incidents')}")
    lines.append(f"stale PRs: {ctx['flow'].get('stale_prs')}")
    lines.append(f"most recent open issues with no maintainer reply: {ctx['flow'].get('unanswered_open_issues', [])[:5]}")
    th = ctx.get("themes", {})
    if th.get("available"):
        lines.append(f"themes reportable={th.get('themes_ok')} provenance={th.get('provenance')} gold_reviewed={th.get('gold_reviewed')}")
        lines.append("pain map [theme, new cur, new prior, open now, median age at close for issues closed this window, days]: "
                     + str([[r['theme'], r['cur'], r['prior'], r['open'], r['median_days_to_close']] for r in th.get('pain_map', [])]))
    return "\n".join(lines)


def _llm(metrics: dict) -> tuple[dict, dict]:
    import anthropic

    client = anthropic.Anthropic()
    d = digest(metrics)
    resp = client.messages.create(
        model=MODEL, max_tokens=2500,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": d}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    text = text[text.index("{"): text.rindex("}") + 1]
    usage = {"model": MODEL, "input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    return json.loads(text), usage


def _rules(metrics: dict) -> dict:
    """Deterministic findings and improvement plan from statuses and deltas. Plain, but always grounded."""
    k = metrics["kpis"]
    v = lambda key: k.get(key, {}).get("value")
    findings, plan = [], []

    def add_f(text, keys, sev="medium"):
        findings.append({"text": text, "metrics": keys, "severity": sev})

    if v("bus_factor") == 1:
        add_f(f"Delivery rests on one person: bus factor is 1 and one author did {v('code_concentration'):.0%} of the code work.",
              ["bus_factor", "code_concentration"], "high")
        plan.append({"text": "Grow a second line of reviewers and mergers", "issue": "Bus factor is 1 on code work and merges.",
                     "outcome": "Releases and reviews continue when the lead maintainer is unavailable.",
                     "actions": ["Name a second merger", "Assign module review owners"], "metrics": ["bus_factor"],
                     "owner": "lead maintainer", "effort": "M", "horizon": "this quarter", "target": "bus_factor ≥ 2"})
    if (s := v("response_within_7d")) is not None and s < 0.5:
        add_f(f"Only {s:.0%} of community issues get a maintainer reply within 7 days.", ["response_within_7d"], "high")
        plan.append({"text": "Run a weekly triage rotation", "issue": f"{s:.0%} of community issues get a maintainer reply within 7 days.",
                     "outcome": "Reporters get a first answer within a week.", "actions": ["Rotate a weekly triager", "Label and reply to new issues"],
                     "metrics": ["response_within_7d"], "owner": "maintainers", "effort": "S", "horizon": "2 weeks",
                     "target": "response_within_7d ≥ 70%"})
    if (o := v("open_issues_over_90d")) and o > 10:
        add_f(f"{o} open issues are older than 90 days.", ["open_issues_over_90d"])
        plan.append({"text": "Close or re-scope stale issues", "issue": f"{o} open issues are older than 90 days.",
                     "outcome": "The tracker reflects current work.", "actions": ["Sweep oldest-first", "Close or relabel each"],
                     "metrics": ["open_issues_over_90d"], "owner": "maintainers", "effort": "S", "horizon": "2 weeks",
                     "target": "open_issues_over_90d ≤ 10"})
    if (d := v("critical_deps_behind")):
        plan.append({"text": "Schedule a pinned-dependency refresh", "issue": f"{d} exact-pinned critical deps are behind PyPI.",
                     "outcome": "Upgrades happen on our schedule, not after a breakage.", "actions": ["Bump pins in one PR", "Run the platform smoke tests"],
                     "metrics": ["critical_deps_behind"], "owner": "release owner", "effort": "S", "horizon": "this quarter",
                     "target": "critical_deps_behind = 0"})
    if (n := k.get("issues_opened")) and n.get("prior"):
        add_f(f"Issue inflow went from {n['prior']} to {n['value']} versus the prior window.", ["issues_opened"])
    for i, r in enumerate(plan, 1):
        r["priority"] = i
    return {"headline": findings[0]["text"] if findings else "", "headline_metrics": findings[0]["metrics"] if findings else [],
            "findings": findings[:3], "recommendations": plan[:5], "slides": {}, "nutshells": _rule_nutshells(metrics)}


def _rule_nutshells(metrics: dict) -> dict:
    """Fallback one-liners: count of good/bad moves per family, citing the moved indicators."""
    out = {}
    for fam in ("flow", "adoption", "code"):
        noisy = ("proxy", "best-effort")
        keys = [k for k in metrics["families"].get(fam, []) if metrics["kpis"][k]["direction"] != "neutral"
                and not any(w in metrics["kpis"][k]["note"] for w in noisy)
                and isinstance(metrics["kpis"][k]["value"], (int, float)) and isinstance(metrics["kpis"][k]["prior"], (int, float))]
        good = [k for k in keys if (metrics["kpis"][k]["value"] < metrics["kpis"][k]["prior"]) == (metrics["kpis"][k]["direction"] == "down")
                and metrics["kpis"][k]["value"] != metrics["kpis"][k]["prior"]]
        bad = [k for k in keys if k not in good and metrics["kpis"][k]["value"] != metrics["kpis"][k]["prior"]]
        lab = lambda k: metrics["kpis"][k]["label"].lower()
        text = (f"Mostly improving; watch {lab(bad[0])}." if len(good) > len(bad) and bad else
                f"Mostly worsening, led by {lab(bad[0])}." if bad else "Stable or improving across the board.")
        out[fam] = {"text": text, "metrics": bad[:1]}
    return out


def narrate(cfg: Config, as_of: str, use_llm: bool = True) -> dict:
    base = Path("data") / cfg.slug
    metrics = json.loads((base / f"metrics-{as_of}.json").read_text())
    h = hashlib.sha1(json.dumps(metrics["kpis"], sort_keys=True).encode()).hexdigest()[:12]
    out_path = base / f"narrative-{as_of}.json"
    override = base / f"narrative-input-{as_of}.json"
    usage = {"model": None, "input_tokens": 0, "output_tokens": 0}
    if override.exists():
        narr = json.loads(override.read_text())
        source = f"{narr.get('author', 'hand-written')} — {override.name}"
    elif use_llm and os.environ.get("ANTHROPIC_API_KEY"):
        if out_path.exists() and json.loads(out_path.read_text()).get("metrics_hash") == h:
            print("narrative up to date (metrics unchanged) — skipping LLM call", file=sys.stderr)
            return json.loads(out_path.read_text())
        narr, usage = _llm(metrics)
        source = f"llm:{MODEL}"
    else:
        narr, source = _rules(metrics), "rules"
    narr, dropped = validate(narr, metrics)
    narr.update(source=source, metrics_hash=h, usage=usage)
    out_path.write_text(json.dumps(narr, indent=1, ensure_ascii=False))
    print(f"narrative: {source}; {len(narr['findings'])} findings, {len(narr['recommendations'])} recs; dropped {len(dropped)}", file=sys.stderr)
    for d in dropped:
        print(f"  dropped {d}", file=sys.stderr)
    print(f"tokens: {usage}", file=sys.stderr)
    return narr
