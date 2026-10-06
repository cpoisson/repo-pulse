from pathlib import Path

import numpy as np

from repo_pulse.classify import calibration as cal
from repo_pulse.config import load
from repo_pulse.metrics import flow
from repo_pulse.metrics.code import bus_factor
from repo_pulse.metrics.util import Windows, quantile, status, weekly, ts

CFG = load(Path(__file__).parent.parent / "configs" / "_template.yaml")
W = Windows.of("2026-10-06", 90)


def _issue(n, created, closed=None, author="user", comments=()):
    return {"number": n, "title": f"t{n}", "body": "", "state": "CLOSED" if closed else "OPEN", "stateReason": None,
            "createdAt": created, "closedAt": closed, "updatedAt": created, "author": author, "labels": [],
            "comments": [{"author": a, "at": t, "assoc": None, "state": None} for a, t in comments]}


def _pr(n, created, author, merged=None, merged_by=None, closed=None):
    return {"number": n, "title": "", "body": "", "state": "MERGED" if merged else "OPEN", "isDraft": False, "createdAt": created,
            "closedAt": closed or merged, "mergedAt": merged, "updatedAt": merged or created, "author": author, "mergedBy": merged_by,
            "labels": [], "files": [], "comments": [], "reviews": []}


def test_windows_are_contiguous_90_day_spans():
    assert (W.cur[1] - W.cur[0]).days == 90 and W.prior[1] == W.cur[0]


def test_flow_counts_and_maintainer_response():
    raw = {
        "issues": [
            _issue(1, "2026-08-01T00:00:00Z", comments=[("maint", "2026-08-01T12:00:00Z")]),   # answered in 0.5 d
            _issue(2, "2026-08-02T00:00:00Z", comments=[("someone", "2026-08-02T01:00:00Z")]),  # non-maintainer reply only
            _issue(3, "2026-05-01T00:00:00Z", closed="2026-08-10T00:00:00Z"),                    # prior-window issue closed now
            _issue(4, "2026-09-01T00:00:00Z", author="maint"),                                   # maintainer's own issue
        ],
        "pulls": [_pr(10, "2026-08-01T00:00:00Z", "ext", merged="2026-08-03T00:00:00Z", merged_by="maint"),
                  _pr(11, "2026-08-05T00:00:00Z", "maint", merged="2026-08-05T06:00:00Z", merged_by="maint"),
                  _pr(12, "2026-08-05T00:00:00Z", "dependabot[bot]", merged="2026-08-06T00:00:00Z", merged_by="maint")],
    }
    k, ctx, _ = flow.compute(CFG, raw, W)
    kp = {x["key"]: x for x in k}
    assert ctx["maintainers"] == ["maint"]
    assert kp["issues_opened"]["value"] == 3 and kp["issues_closed"]["value"] == 1
    assert kp["median_first_response_days"]["value"] == 0.5
    assert kp["response_within_7d"]["value"] == 0.5          # issue 1 yes, issue 2 no (non-maintainer reply doesn't count)
    assert kp["prs_merged"]["value"] == 2                    # bot PR excluded
    assert kp["external_pr_share"]["value"] == 0.5
    assert kp["top_merger_share"]["value"] == 1.0


def test_bus_factor():
    from collections import Counter
    assert bus_factor(Counter(a=70, b=20, c=10)) == 1
    assert bus_factor(Counter(a=30, b=30, c=40)) == 2


def test_status_rules():
    assert status(0.95, {"good": 0.9, "bad": 0.7}) == "green"
    assert status(10, {"good": 2, "bad": 7, "lower_is_better": True}) == "red"
    assert status(None, {"good": 1, "bad": 0}) == "na"


def test_weekly_drops_partial_week():
    s, e = ts("2026-09-07T00:00:00Z"), ts("2026-09-24T00:00:00Z")
    wk = weekly([ts("2026-09-08T10:00:00Z"), ts("2026-09-22T10:00:00Z")], s, e)
    assert [w for w, _ in wk] == ["2026-09-07", "2026-09-14"]  # week of 09-21 is incomplete


def test_quantile():
    assert quantile([1, 2, 3, 4], 0.5) == 2.5 and quantile([], 0.5) is None


def test_calibration_perfect_and_overconfident():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 3, 2000)
    logits = np.eye(3)[y] * 2.0 + rng.normal(0, 1.0, (2000, 3))
    T = cal.fit_temperature(logits * 4, y)               # overconfident logits need T > 1
    assert T > 1.5
    assert cal.ece(cal.softmax(logits * 4, T), y) < cal.ece(cal.softmax(logits * 4), y)


def test_threshold_reaches_precision_on_fit_data():
    p = np.array([[0.9, 0.1], [0.8, 0.2], [0.6, 0.4], [0.55, 0.45]])
    y = np.array([0, 0, 1, 0])
    thr = cal.threshold_for_precision(p, y, 0.9)
    cov, prec = cal.selective(p, y, thr)
    assert prec >= 0.9 and cov == 0.5
