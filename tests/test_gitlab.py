from repo_pulse.collect import gitlab


def test_merge_request_maps_onto_pull_shape():
    m = {"iid": 7, "title": "New app: X", "description": "d" * 2000, "state": "merged", "draft": False,
         "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-03T00:00:00Z", "merged_at": "2026-01-02T00:00:00Z",
         "closed_at": None, "author": {"username": "alice"}, "merge_user": {"username": "bob"}, "labels": ["new app"]}
    p = gitlab._mr(m, [], [])
    assert (p["number"], p["state"], p["author"], p["mergedBy"]) == (7, "MERGED", "alice", "bob")
    assert p["closedAt"] == p["mergedAt"] == "2026-01-02T00:00:00Z"   # GitHub semantics: merged implies closed
    assert len(p["body"]) == gitlab.BODY_CHARS and p["labels"] == ["new app"] and not p["isDraft"]


def test_notes_split_comments_and_approvals():
    notes = [{"author": {"username": "bob"}, "createdAt": "t3", "system": True, "body": "added 1 commit"},
             {"author": {"username": "bob"}, "createdAt": "t1", "system": False, "body": "LGTM"},
             {"author": {"username": "bob"}, "createdAt": "t2", "system": True, "body": "approved this merge request"}]
    comments, reviews = gitlab._split_notes(notes)
    assert [c["at"] for c in comments] == ["t1"] and [(r["at"], r["state"]) for r in reviews] == [("t2", "APPROVED")]
