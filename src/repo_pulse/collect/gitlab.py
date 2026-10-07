"""GitLab collector (gitlab.com REST v4). Emits the same record shapes as github.py, so metrics need no forge logic.

Public projects need no auth; GITLAB_TOKEN (in .env) raises the rate limit (500 -> 2000 requests/min).
Notes come from GraphQL, which (unlike the REST notes endpoint) serves public projects anonymously and batches items.
Unlike the GitHub collector, issues and merge requests are fetched for the lookback span plus everything still open:
busy GitLab projects have tens of thousands of bot MRs, and per-item notes are one call each.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import quote, unquote

import requests

API = "https://gitlab.com/api/v4"
GRAPHQL = "https://gitlab.com/api/graphql"
NOTES_BATCH = 50
BODY_CHARS = 1500
WORKERS = 6
CONCLUSION = {"success": "success", "failed": "failure", "canceled": "cancelled", "skipped": "skipped"}


def project_id(repo: str) -> str:
    return quote(repo, safe="")


def _request(method: str, url: str, **kw) -> requests.Response:
    headers = {"Authorization": f"Bearer {tok}"} if (tok := os.environ.get("GITLAB_TOKEN")) else {}
    for attempt in range(8):
        r = requests.request(method, url, headers=headers, timeout=120, **kw)
        if r.status_code != 429 and r.status_code < 500:
            break
        time.sleep(int(r.headers.get("Retry-After") or 2 ** min(attempt, 5)))
    r.raise_for_status()
    return r


def _get(path: str, **params) -> requests.Response:
    return _request("GET", f"{API}/{path}", params=params)


def _pages(path: str, **params) -> list[dict]:
    out, page = [], 1
    while page:
        r = _get(path, per_page=100, page=page, **params)
        out.extend(r.json())
        page = int(r.headers.get("X-Next-Page") or 0)
    return out


def _total(path: str, **params) -> int | None:
    """X-Total is omitted above 10k results; None then rather than a guess."""
    t = _get(path, per_page=1, **params).headers.get("X-Total")
    return int(t) if t else None


def _pmap(fn: Callable, items: list, progress: str) -> list:
    out = []
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, r in enumerate(ex.map(fn, items), 1):
            out.append(r)
            print(f"  {progress}: {i}/{len(items)}", file=sys.stderr, end="\r")
    if items:
        print(file=sys.stderr)
    return out


def _chunks(since: datetime, days: int = 7) -> list[tuple[str, str]]:
    end = datetime.now(timezone.utc) + timedelta(days=1)
    spans, cur = [], since
    while cur < end:
        nxt = min(cur + timedelta(days=days), end)
        spans.append((cur.isoformat(), nxt.isoformat()))
        cur = nxt
    return spans


def _updated_since(path: str, since: datetime, progress: str, **params) -> list[dict]:
    """Everything updated since `since` (walked in weekly chunks: offset paging slows down deep) plus all open items."""
    lists = _pmap(lambda s: _pages(path, updated_after=s[0], updated_before=s[1], **params), _chunks(since), progress)
    items = {i["iid"]: i for chunk in lists for i in chunk}
    items.update({i["iid"]: i for i in _pages(path, state="opened", **params)})
    return sorted(items.values(), key=lambda i: i["created_at"])


def _user(u: dict | None) -> str | None:
    return (u or {}).get("username")


_NOTES = """query($p:ID!,$iids:[String!]){project(fullPath:$p){%s(iids:$iids,first:%d){
 nodes{iid notes(first:100){nodes{system body createdAt author{username}}}}}}}"""


def _split_notes(notes: list[dict]) -> tuple[list[dict], list[dict]]:
    """Human comments, plus approvals (system notes) as reviews."""
    notes = sorted(notes, key=lambda n: n["createdAt"])
    comments = [{"author": _user(n["author"]), "assoc": None, "at": n["createdAt"], "state": None} for n in notes if not n["system"]]
    reviews = [{"author": _user(n["author"]), "assoc": None, "at": n["createdAt"], "state": "APPROVED"}
               for n in notes if n["system"] and n["body"].startswith("approved this merge request")]
    return comments[:30], reviews[:30]


def _notes(pid: str, kind: str, iids: list[int]) -> dict[int, tuple[list[dict], list[dict]]]:
    """kind: issues | mergeRequests. One GraphQL call per NOTES_BATCH items."""
    def batch(chunk: list[int]) -> list[dict]:
        r = _request("POST", GRAPHQL, json={"query": _NOTES % (kind, len(chunk)),
                                             "variables": {"p": unquote(pid), "iids": [str(i) for i in chunk]}}).json()
        if r.get("errors"):
            raise RuntimeError(r["errors"])
        return r["data"]["project"][kind]["nodes"]

    chunks = [iids[i:i + NOTES_BATCH] for i in range(0, len(iids), NOTES_BATCH)]
    nodes = [n for found in _pmap(batch, chunks, f"{kind} notes (batches)") for n in found]
    return {int(n["iid"]): _split_notes(n["notes"]["nodes"]) for n in nodes}


def _common(i: dict) -> dict:
    return {"number": i["iid"], "title": i["title"], "body": (i.get("description") or "")[:BODY_CHARS],
            "createdAt": i["created_at"], "updatedAt": i["updated_at"], "author": _user(i["author"]),
            "authorAssociation": None, "labels": i.get("labels") or []}


def issues(pid: str, since: datetime) -> list[dict]:
    raw = _updated_since(f"projects/{pid}/issues", since, "issue pages")
    notes = _notes(pid, "issues", [i["iid"] for i in raw if i["user_notes_count"]])
    # no stateReason key: GitLab does not record why an issue was closed
    return [{**_common(i), "state": "OPEN" if i["state"] == "opened" else "CLOSED", "closedAt": i.get("closed_at"),
             "comments": notes.get(i["iid"], ([], []))[0]} for i in raw]


def _mr(m: dict, comments: list[dict], reviews: list[dict]) -> dict:
    return {**_common(m), "state": {"opened": "OPEN", "merged": "MERGED"}.get(m["state"], "CLOSED"),
            "isDraft": bool(m.get("draft") or m.get("work_in_progress")),
            "closedAt": m.get("merged_at") or m.get("closed_at"), "mergedAt": m.get("merged_at"),
            "mergedBy": _user(m.get("merge_user") or m.get("merged_by")), "comments": comments, "reviews": reviews}


def merge_requests(pid: str, since: datetime, is_bot: Callable[[str | None], bool]) -> list[dict]:
    """MRs in the span; notes only for human-authored ones. Each human author's earliest earlier MR is added
    so first-contribution dates (new contributors) are right without fetching the whole history."""
    raw = _updated_since(f"projects/{pid}/merge_requests", since, "MR pages")
    human = [m for m in raw if not is_bot(_user(m["author"]))]
    notes = _notes(pid, "mergeRequests", [m["iid"] for m in human])
    out = [_mr(m, *notes.get(m["iid"], ([], []))) for m in raw]
    first = {}
    for m in human:
        first.setdefault(_user(m["author"]), m["created_at"])
    seen = {m["iid"] for m in raw}

    def earliest(a: str) -> list[dict]:
        return _get(f"projects/{pid}/merge_requests", author_username=a, created_before=first[a],
                    order_by="created_at", sort="asc", per_page=1).json()

    for found in _pmap(earliest, sorted(a for a in first if a), "earlier MRs per author"):
        out += [_mr(m, [], []) for m in found if m["iid"] not in seen]
    return sorted(out, key=lambda p: p["createdAt"])


def repo_meta(pid: str) -> dict:
    p = _get(f"projects/{pid}").json()
    rels = _pages(f"projects/{pid}/releases")
    return {
        "createdAt": p["created_at"], "stargazerCount": p.get("star_count"), "forkCount": p.get("forks_count"),
        "watchers": {"totalCount": None}, "defaultBranchRef": {"name": p.get("default_branch")},
        "issues": {"totalCount": _total(f"projects/{pid}/issues", state="opened")},
        "pullRequests": {"totalCount": _total(f"projects/{pid}/merge_requests", state="opened")},
        "releases": [{"tagName": r["tag_name"], "name": r.get("name"), "publishedAt": r.get("released_at"),
                      "isPrerelease": bool(r.get("upcoming_release"))} for r in rels],
    }


def stars(pid: str) -> list[str]:
    return [s["starred_since"] for s in _pages(f"projects/{pid}/starrers")]


def forks(pid: str) -> list[dict]:
    return [{"createdAt": f["created_at"], "pushedAt": f.get("last_activity_at"), "stargazerCount": f.get("star_count")}
            for f in _pages(f"projects/{pid}/forks", simple="true")]


def pipelines(pid: str, since: datetime, branch: str) -> list[dict]:
    """Default-branch pipelines only (MR pipelines can number one per bot MR), mapped onto Actions-run fields.
    Duration is created -> last update, so it includes queue time."""
    lists = _pmap(lambda s: _pages(f"projects/{pid}/pipelines", ref=branch, updated_after=s[0], updated_before=s[1]),
                  _chunks(since), "pipeline pages")
    runs = {p["id"]: p for chunk in lists for p in chunk}
    return [{"id": p["id"], "name": p.get("name") or "pipeline", "event": p["source"], "head_branch": p["ref"],
             "status": p["status"], "conclusion": CONCLUSION.get(p["status"]), "created_at": p["created_at"],
             "run_started_at": p["created_at"], "updated_at": p["updated_at"]} for p in runs.values()]
