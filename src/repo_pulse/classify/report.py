"""Static HTML report for the bake-off (out/<name>-bakeoff.html)."""
from __future__ import annotations

import html
from pathlib import Path

from ..config import Config


def _pct(x):
    return "—" if x is None else f"{x:.0%}"


def _rel_svg(points: list[list], w: int = 120, h: int = 120) -> str:
    pad = 8
    sx = lambda v: pad + v * (w - 2 * pad)
    sy = lambda v: h - pad - v * (h - 2 * pad)
    dots = "".join(f'<circle cx="{sx(c):.1f}" cy="{sy(a):.1f}" r="{2 + min(n, 30) ** 0.5:.1f}" class="dot"><title>conf {c:.2f} → acc {a:.2f} (n={n})</title></circle>'
                   for c, a, n in points)
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="reliability diagram">'
            f'<rect x="{pad}" y="{pad}" width="{w - 2 * pad}" height="{h - 2 * pad}" class="frame"/>'
            f'<line x1="{sx(0)}" y1="{sy(0)}" x2="{sx(1)}" y2="{sy(1)}" class="diag"/>{dots}</svg>')


def render_bakeoff(cfg: Config, b: dict) -> Path:
    d = b["decision"]
    rows = []
    for f, key in (("type", "types"), ("theme", "themes")):
        rows.append(f"<h2>{f.title()} — {len(b['classes'][f])} classes</h2>")
        dec = d.get(key, {})
        badge = "pass" if dec.get("passed") else "fail"
        rows.append(f'<p class="decision {badge}"><b>Selected: {html.escape(str(dec.get("model", "none")))}</b> — gate '
                    f'{"PASSED" if dec.get("passed") else "NOT PASSED"} ({html.escape(dec.get("reason", ""))})</p>')
        rows.append("<table><thead><tr><th>Model</th><th>Acc</th><th>Macro-F1</th><th>ECE raw → cal</th><th>Brier</th>"
                    f"<th>Coverage @ {b['target_precision']:.0%} prec.</th><th>Test prec.</th><th>s / 1k issues</th><th>$ / 1k</th><th>Reliability</th></tr></thead><tbody>")
        for name, r in b["results"].items():
            if "skipped" in r:
                if f == "type":
                    rows.append(f'<tr class="skip"><td>{html.escape(name)}</td><td colspan="9">skipped — {html.escape(r["skipped"])}</td></tr>')
                continue
            m = r["fields"].get(f)
            if not m:
                continue
            win = ' class="win"' if name == dec.get("model") else ""
            rows.append(f"<tr{win}><td>{html.escape(name)}{' (supervised)' if r['supervised'] else ''}</td><td>{_pct(m['accuracy'])}</td>"
                        f"<td><b>{m['macro_f1']:.2f}</b></td><td>{m['ece_raw']:.3f} → <b>{m['ece']:.3f}</b></td><td>{m['brier']:.3f}</td>"
                        f"<td>{_pct(m['coverage'])}</td><td>{_pct(m['selective_precision'])}</td><td>{r['seconds_per_1k']:.0f}</td>"
                        f"<td>{r['usd_per_1k']:.4f}</td><td>{_rel_svg(m['reliability'])}</td></tr>")
        rows.append("</tbody></table>")
    g = b["gold"]
    warn = "" if g["fully_reviewed"] else (
        f'<p class="decision fail">Gold set not human-reviewed yet ({g["reviewed"]}/{g["n"]}). Labels are one-time LLM pre-labels; '
        f"treat these numbers as provisional until a maintainer reviews <code>out/{cfg.name}-gold-review.html</code>.</p>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Classifier Bake-off</title><style>
:root{{--bg:#fbfaf8;--fg:#1d1d1f;--mut:#6b6b70;--line:#e6e3de;--acc:#b4502a;--ok:#2f7d4f;--bad:#b3261e;--card:#fff}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#151517;--fg:#ececee;--mut:#9a9aa0;--line:#333338;--acc:#e07a4f;--ok:#5cc58a;--bad:#f2766b;--card:#1e1e21}}}}
:root[data-theme=dark]{{--bg:#151517;--fg:#ececee;--mut:#9a9aa0;--line:#333338;--acc:#e07a4f;--ok:#5cc58a;--bad:#f2766b;--card:#1e1e21}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,sans-serif}}main{{max-width:1100px;margin:0 auto;padding:16px}}
table{{width:100%;border-collapse:collapse;margin-bottom:24px;font-variant-numeric:tabular-nums}}th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:middle}}
th{{color:var(--mut);font-weight:500;font-size:12px}}tr.win td{{background:color-mix(in srgb,var(--ok) 10%,transparent)}}tr.skip td{{color:var(--mut)}}
.decision{{padding:8px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card)}}.decision.pass{{border-left:4px solid var(--ok)}}.decision.fail{{border-left:4px solid var(--bad)}}
svg .frame{{fill:none;stroke:var(--line)}}svg .diag{{stroke:var(--mut);stroke-dasharray:3 3}}svg .dot{{fill:var(--acc);fill-opacity:.75}}
.wrap{{overflow-x:auto}}p.m{{color:var(--mut)}}
</style></head><body><main>
<h1>Issue classifier bake-off · {html.escape(cfg.repo)}</h1>
<p class="m">Gold set: {g['n']} issues ({b['n_calib']} calibration / {b['n_test']} test). Temperature scaling and abstain thresholds are fit on the
calibration split; every number below is measured on the held-out test split. Decision rule: {html.escape(d['rule'])}.
Gate: macro-F1 ≥ {cfg.classifier_gate.get('min_macro_f1', .7)}, ECE ≤ {cfg.classifier_gate.get('max_ece', .1)}.</p>
{warn}<div class="wrap">{''.join(rows)}</div>
<p class="m">Reliability: dots are confidence bins (x = mean confidence, y = accuracy, size = count); on the dashed diagonal = perfectly calibrated.
Small test split ⇒ wide uncertainty on per-class numbers.</p></main></body></html>"""
    out = Path("out") / f"{cfg.name}-bakeoff.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page)
    return out
