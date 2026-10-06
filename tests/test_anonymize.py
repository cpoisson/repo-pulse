from repo_pulse.deck.build import _anonymize, _people


def test_people_are_replaced_by_roles_everywhere():
    metrics = {
        "charts": {"mergers": [["alice", 9], ["bob-x", 2]], "pr_authors": [["carol", 5], ["alice", 3]],
                   "commit_authors": [["Alice Liddell", 7]]},
        "context": {"flow": {"maintainers": ["alice", "bob-x"],
                             "flow": {"cur": {"top_author": "carol", "top_merger": "alice"}}}},
    }
    alias = _people(metrics)
    assert alias == {"alice": "maintainer A", "bob-x": "maintainer B", "carol": "contributor 1", "Alice Liddell": "author 1"}
    data = {"label": "Share of merges by top merger (alice)", "chart": [["bob-x", 2]], "who": "carol",
            "text": "alice-bot and malice are other words", "commits": [["Alice Liddell", 7]]}
    out = _anonymize(data, alias)
    assert out["label"] == "Share of merges by top merger (maintainer A)"
    assert out["chart"] == [["maintainer B", 2]] and out["who"] == "contributor 1"
    assert out["text"] == "alice-bot and malice are other words"  # whole names only
    assert out["commits"] == [["author 1", 7]]
