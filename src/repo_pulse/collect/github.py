"""GitHub collector. Uses the `gh` CLI for auth (no token handling here)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable

BODY_CHARS = 1500


def _gh(args: list[str], stdin: str | None = None) -> str:
    r = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()[:500]}")
    return r.stdout


def gql(query: str, **variables) -> dict:
    out = json.loads(_gh(["api", "graphql", "--input", "-"], json.dumps({"query": query, "variables": variables})))
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]


def _paginate(query: str, path: list[str], owner: str, name: str, progress: str = "",
              stop: Callable[[list[dict]], bool] | None = None) -> list[dict]:
    """`stop(page_nodes)` ends paging early (for queries ordered newest first)."""
    nodes, cursor, page = [], None, 0
    while True:
        data = gql(query, owner=owner, name=name, cursor=cursor)
        conn = data
        for k in path:
            conn = conn[k]
        batch = conn.get("nodes") or conn.get("edges") or []
        nodes.extend(batch)
        page += 1
        if progress:
            print(f"  {progress}: {len(nodes)}", file=sys.stderr, end="\r")
        if not conn["pageInfo"]["hasNextPage"] or (stop and stop(batch)):
            break
        cursor = conn["pageInfo"]["endCursor"]
    if progress:
        print(file=sys.stderr)
    return nodes


_ISSUES = """
query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){
 issues(first:50,after:$cursor,orderBy:{field:CREATED_AT,direction:ASC}){pageInfo{hasNextPage endCursor}
  nodes{number title body state stateReason createdAt closedAt updatedAt author{login} authorAssociation
   labels(first:10){nodes{name}}
   comments(first:30){totalCount nodes{author{login} authorAssociation createdAt}}}}}}"""

_PR_FIELDS = """number title body state isDraft createdAt closedAt mergedAt updatedAt author{login} authorAssociation
   mergedBy{login} additions deletions changedFiles labels(first:10){nodes{name}}
   files(first:100){nodes{path additions deletions}}
   comments(first:30){nodes{author{login} authorAssociation createdAt}}
   reviews(first:30){nodes{author{login} authorAssociation submittedAt state}}"""

_PRS = """
query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){
 pullRequests(first:25,after:$cursor,%s){pageInfo{hasNextPage endCursor} nodes{%s}}}}"""

# Full history, cheap fields only: enough for first-contribution dates and who merged in the last year.
_PR_LIGHT = """number title state isDraft createdAt closedAt mergedAt updatedAt author{login} authorAssociation mergedBy{login}"""

_STARS = """
query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){
 stargazers(first:100,after:$cursor){pageInfo{hasNextPage endCursor} edges{starredAt}}}}"""

_FORKS = """
query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){
 forks(first:100,after:$cursor){pageInfo{hasNextPage endCursor} nodes{createdAt pushedAt stargazerCount}}}}"""

_REPO = """
query($owner:String!,$name:String!){repository(owner:$owner,name:$name){
 createdAt stargazerCount forkCount watchers{totalCount} defaultBranchRef{name}
 issues(states:OPEN){totalCount} pullRequests(states:OPEN){totalCount}
 releases(first:50,orderBy:{field:CREATED_AT,direction:DESC}){nodes{tagName name publishedAt isPrerelease}}
 dependencyGraphManifests{totalCount}}}"""


def _flatten(item: dict) -> dict:
    item = dict(item)
    if item.get("body"):
        item["body"] = item["body"][:BODY_CHARS]
    item["author"] = (item.get("author") or {}).get("login")
    if "mergedBy" in item:
        item["mergedBy"] = (item.get("mergedBy") or {}).get("login")
    item["labels"] = [l["name"] for l in item.get("labels", {}).get("nodes", [])]
    for key in ("comments", "reviews"):
        if key in item:
            item[key] = [
                {"author": (n.get("author") or {}).get("login"), "assoc": n.get("authorAssociation"),
                 "at": n.get("createdAt") or n.get("submittedAt"), "state": n.get("state")}
                for n in item[key]["nodes"]
            ]
    if "files" in item:
        item["files"] = item["files"]["nodes"] if item["files"] else []
    return item


def issues(owner: str, name: str) -> list[dict]:
    return [_flatten(n) for n in _paginate(_ISSUES, ["repository", "issues"], owner, name, "issues")]


def pulls(owner: str, name: str, since: datetime | None = None) -> list[dict]:
    """With `since`, full detail (files, comments, reviews) only for PRs updated since then or still open;
    older PRs come from a light pass so first-contribution and maintainer inference stay exact."""
    path = ["repository", "pullRequests"]
    if since is None:
        return [_flatten(n) for n in _paginate(_PRS % ("orderBy:{field:CREATED_AT,direction:ASC}", _PR_FIELDS), path, owner, name, "pull requests")]
    cutoff = since.isoformat()
    recent = _paginate(_PRS % ("orderBy:{field:UPDATED_AT,direction:DESC}", _PR_FIELDS), path, owner, name, "recent pull requests",
                       stop=lambda batch: bool(batch) and batch[-1]["updatedAt"] < cutoff)
    detailed = {n["number"]: n for n in recent if n["updatedAt"] >= cutoff}
    detailed.update({n["number"]: n for n in _paginate(_PRS % ("states:OPEN", _PR_FIELDS), path, owner, name, "open pull requests")})
    light = _paginate(_PRS.replace("first:25", "first:100") % ("orderBy:{field:CREATED_AT,direction:ASC}", _PR_LIGHT), path, owner, name, "pull request history")
    out = [_flatten(detailed.get(n["number"], n)) for n in light]
    known = {n["number"] for n in light}
    out += [_flatten(n) for num, n in detailed.items() if num not in known]   # opened during the light pass
    for item in out:
        item.setdefault("comments", [])
        item.setdefault("reviews", [])
        item.setdefault("labels", [])
    return sorted(out, key=lambda p: p["createdAt"])


def stars(owner: str, name: str, cap: int = 40000) -> list[str]:
    """starredAt timestamps. Very large repos are skipped (too many calls); some repos return none."""
    total = gql("query($owner:String!,$name:String!){repository(owner:$owner,name:$name){stargazerCount}}", owner=owner, name=name)
    if total["repository"]["stargazerCount"] > cap:
        return []
    return [e["starredAt"] for e in _paginate(_STARS, ["repository", "stargazers"], owner, name, "stars")]


def forks(owner: str, name: str) -> list[dict]:
    return _paginate(_FORKS, ["repository", "forks"], owner, name, "forks")


def repo_meta(owner: str, name: str) -> dict:
    r = gql(_REPO, owner=owner, name=name)["repository"]
    r["releases"] = r["releases"]["nodes"]
    return r


def ci_runs(owner: str, name: str, days: int, chunk_days: int = 7) -> list[dict]:
    """The runs endpoint caps any single query at 1000 results, so walk the window in weekly chunks."""
    end = datetime.now(timezone.utc).date() + timedelta(days=1)
    start = end - timedelta(days=days)
    runs, cur = [], start
    while cur < end:
        nxt = min(cur + timedelta(days=chunk_days), end)
        out = _gh(["api", "--paginate", f"repos/{owner}/{name}/actions/runs?per_page=100&created={cur}..{nxt - timedelta(days=1)}",
                   "-q", ".workflow_runs[] | {id, name, event, head_branch, status, conclusion, created_at, run_started_at, updated_at}"])
        runs.extend(json.loads(line) for line in out.splitlines() if line.strip())
        print(f"  ci runs: {len(runs)}", file=sys.stderr, end="\r")
        cur = nxt
    print(file=sys.stderr)
    return list({r["id"]: r for r in runs}.values())


def dependents_count(owner: str, name: str) -> int | None:
    """Best-effort scrape of the public 'Used by' count (no API exists)."""
    import re

    import requests

    try:
        html = requests.get(f"https://github.com/{owner}/{name}/network/dependents", timeout=20).text
        m = re.search(r"([\d,]+)\s*\n?\s*Repositories", html)
        return int(m.group(1).replace(",", "")) if m else None
    except Exception:
        return None
