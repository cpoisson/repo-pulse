"""Production classification for an edition.

Gold labels are used as-is where they exist. Every other issue is labelled by the model the bake-off selected,
with its fitted temperature and abstain threshold. Low-confidence items stay unlabelled (never forced).
Results are cached by issue number + updatedAt so reruns only score new or edited issues.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from ..collect.cache import load_all
from ..config import Config
from . import calibration as cal
from . import gold as gold_mod
from . import issue_text
from .models import registry


def _key(item: dict, model: str) -> str:
    return hashlib.sha1(f"{item['number']}|{item['updatedAt']}|{model}".encode()).hexdigest()[:16]


def classify_corpus(cfg: Config, as_of: str, model: str | None = None, mode: str | None = None) -> dict:
    base = Path("data") / cfg.slug
    raw = load_all(cfg.slug, as_of)
    g = gold_mod.load(cfg)["items"]
    decision = json.loads((base / "classifier.json").read_text()) if (base / "classifier.json").exists() else {}
    mode = mode or cfg.classifier
    bake = base / "bakeoff.json"
    if bake.exists() and decision.get("mode") != mode:
        # re-decide from recorded results so switching mode never needs a new bake-off
        from .bakeoff import decide

        b = json.loads(bake.read_text())
        decision = decide(cfg, b["results"], b["gold"], mode)
        (base / "classifier.json").write_text(json.dumps(decision, indent=1))
        print(f"classifier mode {mode}: types={decision['types'].get('model')}, themes={decision['themes'].get('model')}", file=sys.stderr)
    labels = {"type": cfg.issue_types, "theme": cfg.themes}
    classes = {f: list(v) for f, v in labels.items()}
    cache_path = base / "label_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    out: dict[str, dict] = {}
    todo = []
    for it in raw["issues"]:
        n = str(it["number"])
        if n in g:
            out[n] = {"type": g[n]["type"], "theme": g[n]["theme"], "source": "gold-reviewed" if g[n].get("reviewed") else "gold-prelabel"}
        else:
            todo.append(it)

    reg = registry()
    scored: dict[tuple, dict] = {}   # one scoring pass per (model, pending set): a single API call answers both fields
    for f, key in (("type", "types"), ("theme", "themes")):
        dec = decision.get(key, {})
        name = model or dec.get("model")
        if not name or not todo:
            continue
        pending = [it for it in todo if _key(it, name) + f not in cache]
        if pending:
            m = reg[name]
            texts = [issue_text(it) for it in pending]
            if m.supervised:
                gnums = [n for n in g if g[n]["split"] == "calib"]
                issues = {str(i["number"]): i for i in raw["issues"]}
                gnums = [n for n in gnums if n in issues]
                scores = m.fit_predict([issue_text(issues[n]) for n in gnums], {ff: [g[n][ff] for n in gnums] for ff in labels},
                                       texts, labels)[f]
            else:
                memo = (name, tuple(it["number"] for it in pending))
                if memo not in scored:
                    scored[memo] = m.score(texts, labels)
                scores = scored[memo][f]
            p = cal.softmax(scores, dec.get("temperature", 1.0))
            for it, row in zip(pending, p):
                cache[_key(it, name) + f] = [classes[f][int(row.argmax())], float(row.max())]
            print(f"  classified {len(pending)} new/edited issues ({f}) with {name}", file=sys.stderr)
        thr = dec.get("threshold", 0.0)
        for it in todo:
            lab, conf = cache[_key(it, name) + f]
            rec = out.setdefault(str(it["number"]), {"source": f"model:{name}"})
            rec[f] = lab if conf >= thr else None
            rec[f"{f}_conf"] = round(conf, 3)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache))
    (base / "labels.json").write_text(json.dumps(out, indent=1))
    src = {}
    for v in out.values():
        src[v["source"]] = src.get(v["source"], 0) + 1
    print(f"labels: {src}", file=sys.stderr)
    return out
