from datetime import datetime, timezone

from repo_pulse.collect import github


def _pr(n, created, updated, state="MERGED", full=False):
    pr = {"number": n, "title": f"pr {n}", "state": state, "isDraft": False, "createdAt": created, "closedAt": updated,
          "mergedAt": updated if state == "MERGED" else None, "updatedAt": updated, "author": {"login": f"u{n}"},
          "authorAssociation": "NONE", "mergedBy": {"login": "m"}}
    if full:
        pr |= {"body": "b", "labels": {"nodes": [{"name": "bug"}]}, "files": {"nodes": []},
               "comments": {"nodes": [{"author": {"login": "m"}, "authorAssociation": "MEMBER", "createdAt": updated}]},
               "reviews": {"nodes": []}}
    return pr


def test_windowed_pulls_detail_recent_and_open_only(monkeypatch):
    old, recent, still_open = _pr(1, "2024-01-01", "2024-01-02"), _pr(2, "2026-09-01", "2026-09-02"), _pr(3, "2024-03-01", "2024-03-02", "OPEN")
    pages = {"UPDATED_AT": [_pr(2, "2026-09-01", "2026-09-02", full=True), _pr(1, "2024-01-01", "2024-01-02", full=True)],
             "states:OPEN": [_pr(3, "2024-03-01", "2024-03-02", "OPEN", full=True)],
             "first:100": [old, still_open, recent]}

    def fake(query, *a, stop=None, **k):
        return next(v for key, v in pages.items() if key in query)

    monkeypatch.setattr(github, "_paginate", fake)
    out = {p["number"]: p for p in github.pulls("o", "n", since=datetime(2026, 4, 1, tzinfo=timezone.utc))}
    assert sorted(out) == [1, 2, 3]
    assert out[1]["comments"] == [] and out[1]["author"] == "u1" and out[1]["mergedBy"] == "m"   # light record
    assert out[2]["comments"][0]["author"] == "m" and out[2]["labels"] == ["bug"]                 # detailed: updated in span
    assert out[3]["comments"] and out[3]["state"] == "OPEN"                                         # detailed: still open
