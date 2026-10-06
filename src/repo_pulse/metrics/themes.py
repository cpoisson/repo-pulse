"""Issue types & themes from classifier labels. Themes are only reported if the classifier passed the gate."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ..config import Config
from .util import Windows, days, kpi, quantile, ratio, ts, within


def load_labels(cfg: Config) -> tuple[dict, dict]:
    base = Path("data") / cfg.slug
    labels = json.loads((base / "labels.json").read_text()) if (base / "labels.json").exists() else {}
    gate = json.loads((base / "classifier.json").read_text()) if (base / "classifier.json").exists() else {}
    return labels, gate


def _ci_counts(labels: list[str], confusion: dict | None, classes: list[str], n_boot: int = 500, seed: int = 0):
    """Bootstrap CI on predicted counts, correcting with P(true | predicted) from the test confusion matrix."""
    counts = Counter(labels)
    if not confusion:
        return {c: [counts.get(c, 0), None, None] for c in classes}
    rng = np.random.default_rng(seed)
    # rows: predicted, cols: true -> column-normalised posterior
    post = {}
    for pred in classes:
        row = np.array([confusion.get(pred, {}).get(t, 0) for t in classes], dtype=float) + 0.5  # Jeffreys-ish smoothing
        post[pred] = row / row.sum()
    sims = np.zeros((n_boot, len(classes)))
    for b in range(n_boot):
        for pred, n in counts.items():
            if pred in post and n:
                p = rng.dirichlet(post[pred] * 20)
                sims[b] += rng.multinomial(n, p)
    out = {}
    for j, c in enumerate(classes):
        lo, hi = np.percentile(sims[:, j], [5, 95])
        out[c] = [counts.get(c, 0), int(lo), int(hi)]
    return out


def compute(cfg: Config, raw: dict, w: Windows) -> tuple[list[dict], dict, dict]:
    labels, gate = load_labels(cfg)
    # Labels from a model that failed its gate are not trusted: treat them as unclassified.
    for lab in labels.values():
        if lab.get("source", "").startswith("model:"):
            for field, key in (("type", "types"), ("theme", "themes")):
                if not gate.get(key, {}).get("passed"):
                    lab[field] = None
    k, ctx, charts = [], {"gate": gate}, {}
    if not labels:
        ctx["available"] = False
        return k, ctx, charts
    ctx["available"] = True
    issues = {str(i["number"]): i for i in raw.get("issues", [])}
    items = [(issues[n], lab) for n, lab in labels.items() if n in issues]
    gate_types = bool(gate.get("types", {}).get("passed"))
    gate_themes = bool(gate.get("themes", {}).get("passed"))

    def in_win(win):
        return [(i, lab) for i, lab in items if within(ts(i["createdAt"]), win)]

    cur_items = in_win(w.cur)
    model_cur = [lab for _, lab in cur_items if lab.get("source", "").startswith("model:")]
    ctx["provenance"] = dict(Counter(lab.get("source", "?") for _, lab in cur_items))
    ctx["gold_reviewed"] = bool(gate.get("gold_reviewed"))
    # Model labels only count if the model passed the gate; gold labels are used as-is.
    share_model = len(model_cur) / max(len(cur_items), 1)
    types_ok = gate_types or share_model <= 0.10
    themes_ok = gate_themes or share_model <= 0.10
    ctx["types_ok"], ctx["themes_ok"] = types_ok, themes_ok

    def by_window(win, field):
        return [lab.get(field) for i, lab in in_win(win)]

    for field, classes, ok in (("type", list(cfg.issue_types), types_ok), ("theme", list(cfg.themes), themes_ok)):
        cls = classes + ["unclassified"]
        gold_cur = Counter((lab.get(field) or "unclassified") for _, lab in cur_items if not lab.get("source", "").startswith("model:"))
        mod_cur = [(lab.get(field) or "unclassified") for lab in model_cur]
        conf = gate.get(f"{field}s", {}).get("confusion")
        ci = _ci_counts(mod_cur, conf, cls) if mod_cur else {c: [0, 0, 0] for c in cls}
        cur = {c: [gold_cur.get(c, 0) + ci[c][0],
                   None if ci[c][1] is None else gold_cur.get(c, 0) + ci[c][1],
                   None if ci[c][2] is None else gold_cur.get(c, 0) + ci[c][2]] for c in cls}
        prior = [x or "unclassified" for x in by_window(w.prior, field)]
        charts[f"{field}_counts"] = {"classes": cls, "cur": cur, "prior": dict(Counter(prior)), "reportable": ok}

    # pain map per theme (current window + still-open now)
    pain = []
    for th in cfg.themes:
        its = [i for i, lab in items if lab.get("theme") == th]
        cur = [i for i in its if within(ts(i["createdAt"]), w.cur)]
        prior = [i for i in its if within(ts(i["createdAt"]), w.prior)]
        open_ = [i for i in its if not i["closedAt"]]
        ttr = [days(ts(i["createdAt"]), ts(i["closedAt"])) for i in its if i["closedAt"] and within(ts(i["closedAt"]), w.cur)]
        examples = sorted(open_ or cur, key=lambda i: -len(i.get("comments") or []))[:3]
        pain.append({"theme": th, "cur": len(cur), "prior": len(prior), "open": len(open_), "open_share": ratio(len(open_), len(its)),
                     "median_days_to_close": quantile(ttr, 0.5), "examples": [[i["number"], i["title"]] for i in examples]})
    ctx["pain_map"] = sorted(pain, key=lambda r: -r["cur"])

    bug_share = ratio(sum(1 for x in by_window(w.cur, "type") if x == "bug"), len(by_window(w.cur, "type")))
    bug_prior = ratio(sum(1 for x in by_window(w.prior, "type") if x == "bug"), len(by_window(w.prior, "type")))
    prov = ", ".join(f"{k_}: {v}" for k_, v in ctx["provenance"].items())
    k.append(kpi("bug_share", "Share of new issues that are bugs", bug_share if types_ok else None, bug_prior if types_ok else None,
                 "ratio", lower_is_better=True, note=f"labels — {prov}"))
    abst = [lab for _, lab in cur_items]
    k.append(kpi("classifier_coverage", "New issues with a confident theme label", ratio(sum(1 for l in abst if l.get("theme")), len(abst)),
                 unit="ratio", note=f"labels — {prov}"))
    if themes_ok and ctx["pain_map"]:
        top = ctx["pain_map"][0]
        k.append(kpi("top_theme_share", f"Top issue theme share ({top['theme']})", ratio(top["cur"], sum(r["cur"] for r in pain)), unit="ratio"))
    return k, ctx, charts
