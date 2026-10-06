"""Bake-off: score every candidate on the gold set, calibrate on the calib split, evaluate on the test split,
pick the winner per field with an explicit rule, and record the gate decision used by the deck."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from ..collect.cache import load_all
from ..config import Config
from . import calibration as cal
from . import gold as gold_mod
from . import issue_text
from .models import registry

F1_TOLERANCE = 0.03  # "within 3 F1 points of the best"


def _rank(name: str, res: dict, field: str) -> tuple:
    """Among eligible models: no/lowest API spend first, then the most issues decided confidently at the
    target precision (decision efficiency), then measured wall time."""
    f = res["fields"][field]
    return (res.get("usd_per_1k", 0.0), -(f.get("coverage") or 0.0), res.get("seconds_per_1k", 0))


def _oof(model, texts, y, labels, folds: int):
    """Out-of-fold log-scores on the calibration split for supervised models."""
    n = len(texts)
    idx = np.arange(n)
    rng = np.random.default_rng(0)
    rng.shuffle(idx)
    out = {f: np.zeros((n, len(labels[f]))) for f in ("type", "theme")}
    for k in range(folds):
        te = idx[k::folds]
        tr = np.setdiff1d(idx, te)
        pred = model.fit_predict([texts[i] for i in tr], {f: [y[f][i] for i in tr] for f in y}, [texts[i] for i in te], labels)
        for f in out:
            out[f][te] = pred[f]
    return out


def run_bakeoff(cfg: Config, as_of: str, models: list[str] | None = None, mode: str | None = None) -> Path:
    mode = mode or cfg.classifier
    raw = load_all(cfg.slug, as_of)
    g = gold_mod.load(cfg)
    gstat = gold_mod.status(g)
    issues = {str(i["number"]): i for i in raw["issues"]}
    nums = [n for n in sorted(g["items"], key=int) if n in issues]
    labels = {"type": cfg.issue_types, "theme": cfg.themes}
    classes = {f: list(labels[f]) for f in labels}
    texts = [issue_text(issues[n]) for n in nums]
    y = {f: np.array([classes[f].index(g["items"][n][f]) for n in nums]) for f in labels}
    split = np.array([g["items"][n]["split"] for n in nums])
    cal_m, test_m = split == "calib", split == "test"
    target = cfg.classifier_gate.get("target_precision", 0.85)

    reg = registry()
    names = models or list(reg)
    if mode == "local":  # free mode never spends API tokens, even if a key is configured
        names = [n for n in names if not reg[n].api]
    prev_path = Path("data") / cfg.slug / "bakeoff.json"
    prev = json.loads(prev_path.read_text()) if prev_path.exists() and models else {}
    same_gold = prev.get("gold", {}).get("n") == gstat["n"] and prev.get("gold", {}).get("reviewed") == gstat["reviewed"]
    results: dict[str, dict] = {k: v for k, v in prev.get("results", {}).items() if k in reg and k not in names} if same_gold else {}
    for name in names:
        m = reg[name]
        ok, why = m.available()
        if not ok:
            results[name] = {"skipped": why}
            print(f"- {name}: skipped ({why})", file=sys.stderr)
            continue
        print(f"- {name} ...", file=sys.stderr)
        t0 = time.time()
        try:
            if m.supervised:
                ytxt = {f: [classes[f][v] for v in y[f]] for f in y}
                ci = np.where(cal_m)[0]
                ti = np.where(test_m)[0]
                folds = 5 if "LR" in name else 3
                oof = _oof(m, [texts[i] for i in ci], {f: [ytxt[f][i] for i in ci] for f in y}, labels, folds)
                pred = m.fit_predict([texts[i] for i in ci], {f: [ytxt[f][i] for i in ci] for f in y}, [texts[i] for i in ti], labels)
                scores = {}
                for f in ("type", "theme"):
                    s = np.zeros((len(texts), len(classes[f])))
                    s[ci], s[ti] = oof[f], pred[f]
                    scores[f] = s
            else:
                scores = m.score(texts, labels)
        except Exception as e:  # a broken candidate must not sink the bake-off
            results[name] = {"skipped": f"error: {type(e).__name__}: {str(e)[:200]}"}
            print(f"  ! {name} failed: {e}", file=sys.stderr)
            continue
        secs = time.time() - t0
        tokens = getattr(m, "tokens", 0)
        res = {"seconds": round(secs, 1), "seconds_per_1k": round(secs / len(texts) * 1000, 1), "tokens": tokens,
               "usd_per_1k": round(tokens / len(texts) * 1000 / 1e6 * getattr(m, "PRICE_PER_M_INPUT", 0), 4),
               "supervised": m.supervised, "fields": {}}
        for f in ("type", "theme"):
            s = scores.get(f)
            if s is None:
                continue
            raw_p = cal.softmax(s[test_m])
            T = cal.fit_temperature(s[cal_m], y[f][cal_m])
            p_cal, p_test = cal.softmax(s[cal_m], T), cal.softmax(s[test_m], T)
            yt = y[f][test_m]
            pred = p_test.argmax(1)
            f1, per = cal.macro_f1(pred, yt, len(classes[f]))
            thr = cal.threshold_for_precision(p_cal, y[f][cal_m], target)
            cov, prec = cal.selective(p_test, yt, thr)
            res["fields"][f] = {
                "accuracy": round(float((pred == yt).mean()), 4), "macro_f1": f1, "per_class_f1": per,
                "ece_raw": cal.ece(raw_p, yt), "ece": cal.ece(p_test, yt), "brier": cal.brier(p_test, yt), "temperature": round(T, 3),
                "threshold": thr, "coverage": cov, "selective_precision": prec,
                "reliability": cal.reliability(p_test, yt), "confusion": cal.confusion(pred, yt, classes[f]),
            }
        results[name] = res
        print(f"  {name}: " + ", ".join(f"{f} F1={v['macro_f1']:.2f} ECE={v['ece']:.3f} cov@{target:.0%}={v['coverage']}"
                                      for f, v in res["fields"].items()), file=sys.stderr)

    decision = decide(cfg, results, gstat, mode)
    out = {"as_of": as_of, "gold": gstat, "n_test": int(test_m.sum()), "n_calib": int(cal_m.sum()),
           "target_precision": target, "results": results, "decision": decision, "classes": classes}
    base = Path("data") / cfg.slug
    base.mkdir(parents=True, exist_ok=True)
    (base / "bakeoff.json").write_text(json.dumps(out, indent=1))
    (base / "classifier.json").write_text(json.dumps(decision, indent=1))
    from .report import render_bakeoff

    return render_bakeoff(cfg, out)


MODES = ("local", "auto", "jev")


def decide(cfg: Config, results: dict, gstat: dict, mode: str | None = None) -> dict:
    """Pick the classifier per field from recorded bake-off results under a mode:
    local = free local models only (default); auto = every measured model competes; jev = Jev for both fields."""
    mode = mode or cfg.classifier
    if mode not in MODES:
        raise ValueError(f"classifier mode must be one of {MODES}, got {mode!r}")
    api = {n for n, m in registry().items() if m.api}
    if mode == "local":
        results = {n: r for n, r in results.items() if n not in api}
    elif mode == "jev":
        if "fields" not in results.get("typesafe-jev", {}):
            raise RuntimeError("classifier: jev, but Jev has no bake-off results (set TYPESAFE_API_KEY and run "
                               "`repo-pulse bakeoff --models typesafe-jev`)")
        results = {"typesafe-jev": results["typesafe-jev"]}
    out = _decide(cfg, results, gstat)
    out["mode"] = mode
    return out


def _decide(cfg: Config, results: dict, gstat: dict) -> dict:
    gate = cfg.classifier_gate
    decision = {"gold_reviewed": gstat["fully_reviewed"], "rule":
                (f"among candidates within {F1_TOLERANCE:.0%} macro-F1 of the best with calibrated ECE ≤ {gate.get('max_ece', 0.1)}: "
                 f"lowest API cost, then highest coverage at {gate.get('target_precision', 0.85):.0%} precision, then fastest")}
    for f, key in (("type", "types"), ("theme", "themes")):
        cands = {n: r for n, r in results.items() if "fields" in r and f in r["fields"] and n != "rules"}
        if not cands:
            decision[key] = {"passed": False, "reason": "no candidate produced scores"}
            continue
        best_f1 = max(r["fields"][f]["macro_f1"] for r in cands.values())
        eligible = [n for n, r in cands.items()
                    if r["fields"][f]["macro_f1"] >= best_f1 - F1_TOLERANCE and r["fields"][f]["ece"] <= gate.get("max_ece", 0.1)]
        pool = eligible or [max(cands, key=lambda n: cands[n]["fields"][f]["macro_f1"])]
        # a forced single candidate (jev mode) is selected even if outside tolerance/ECE; the gate still reports it
        win = min(pool, key=lambda n: _rank(n, cands[n], f))
        m = cands[win]["fields"][f]
        passed = m["macro_f1"] >= gate.get("min_macro_f1", 0.7) and m["ece"] <= gate.get("max_ece", 0.1)
        reasons = []
        if m["macro_f1"] < gate.get("min_macro_f1", 0.7):
            reasons.append(f"macro-F1 {m['macro_f1']:.2f} < {gate.get('min_macro_f1', 0.7)}")
        if m["ece"] > gate.get("max_ece", 0.1):
            reasons.append(f"ECE {m['ece']:.3f} > {gate.get('max_ece', 0.1)}")
        decision[key] = {"model": win, "passed": passed, "reason": "; ".join(reasons) or "meets gate",
                         "macro_f1": m["macro_f1"], "ece": m["ece"], "accuracy": m["accuracy"], "temperature": m["temperature"],
                         "threshold": m["threshold"], "coverage": m["coverage"], "selective_precision": m["selective_precision"],
                         "confusion": m["confusion"], "eligible": eligible, "best_f1": best_f1}
    return decision
