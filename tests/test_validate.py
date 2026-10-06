from repo_pulse.llm.validate import check_claim, validate

KPIS = {
    "response_within_7d": {"value": 0.212, "prior": 0.333, "delta": -0.121, "unit": "ratio", "label": "Issues answered within 7 days", "note": ""},
    "issues_opened": {"value": 97, "prior": 13, "delta": 84, "unit": "", "label": "Issues opened", "note": ""},
    "median_first_response_days": {"value": 0.94, "prior": 15.95, "delta": -15.01, "unit": "days", "label": "Median first response", "note": ""},
}


def test_accepts_restated_numbers():
    ok, why = check_claim({"text": "Only 21% answered within 7 days (33% prior).", "metrics": ["response_within_7d"]}, KPIS)
    assert ok, why


def test_accepts_percent_change_and_ratio():
    assert check_claim({"text": "Inflow grew 646% to 97 issues, about 7.5 times the prior 13.", "metrics": ["issues_opened"]}, KPIS)[0]


def test_rejects_fabricated_number():
    ok, why = check_claim({"text": "Only 45% answered within 7 days.", "metrics": ["response_within_7d"]}, KPIS)
    assert not ok and "45" in why


def test_known_limit_number_matching_is_not_semantic():
    # 12 is the real delta (-12 pts), so a sentence that misuses it as the level still passes.
    # The check guarantees numbers come from the cited metrics, not that they are described correctly.
    assert check_claim({"text": "Only 12% answered within 7 days.", "metrics": ["response_within_7d"]}, KPIS)[0]


def test_rejects_number_from_uncited_metric():
    ok, _ = check_claim({"text": "97 issues were opened.", "metrics": ["response_within_7d"]}, KPIS)
    assert not ok


def test_rejects_unknown_metric_key():
    ok, why = check_claim({"text": "Things improved.", "metrics": ["made_up_metric"]}, KPIS)
    assert not ok and "unknown" in why


def test_targets_are_goals_not_claims():
    assert check_claim({"text": "Run triage", "why": "21% answered.", "target": "at least 70%", "metrics": ["response_within_7d"]}, KPIS)[0]


def test_validate_drops_only_bad_claims():
    narr = {"findings": [{"text": "97 issues opened.", "metrics": ["issues_opened"]},
                         {"text": "Response time is 3 days.", "metrics": ["median_first_response_days"]}],
            "recommendations": [], "slides": {"flow": {"so_what": "Inflow hit 500.", "metrics": ["issues_opened"]}}}
    out, dropped = validate(narr, {"kpis": KPIS, "context": {}})
    assert len(out["findings"]) == 1 and out["slides"]["flow"]["so_what"] == "" and len(dropped) == 2
