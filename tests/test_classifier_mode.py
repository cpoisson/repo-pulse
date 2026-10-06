from pathlib import Path

import pytest

from repo_pulse.classify.bakeoff import decide
from repo_pulse.config import load

CFG = load(Path(__file__).parent.parent / "configs" / "_template.yaml")
GOLD = {"fully_reviewed": False}


def _res(f1, ece=0.05, cov=0.9, usd=0.0):
    field = {"macro_f1": f1, "ece": ece, "accuracy": f1, "temperature": 1.0, "threshold": 0.5, "coverage": cov,
             "selective_precision": 0.9, "confusion": {}}
    return {"fields": {"type": dict(field), "theme": dict(field)}, "usd_per_1k": usd, "seconds_per_1k": 10, "supervised": False}


RESULTS = {"ModernBERT-base_issue-type": _res(0.79), "bge-base-en-v1.5+LR": _res(0.60),
           "typesafe-jev": _res(0.88, usd=0.05)}


def test_local_mode_never_selects_api_models():
    d = decide(CFG, RESULTS, GOLD, "local")
    assert d["mode"] == "local" and d["types"]["model"] != "typesafe-jev" and d["themes"]["model"] != "typesafe-jev"


def test_auto_mode_lets_the_measured_winner_win():
    d = decide(CFG, RESULTS, GOLD, "auto")
    assert d["types"]["model"] == "typesafe-jev"


def test_jev_mode_forces_jev_and_still_reports_the_gate():
    weak = dict(RESULTS, **{"typesafe-jev": _res(0.5, usd=0.05)})
    d = decide(CFG, weak, GOLD, "jev")
    assert d["types"]["model"] == "typesafe-jev" and d["types"]["passed"] is False


def test_jev_mode_without_results_fails_loudly():
    with pytest.raises(RuntimeError):
        decide(CFG, {k: v for k, v in RESULTS.items() if k != "typesafe-jev"}, GOLD, "jev")
