"""HF Hub reach: Spaces and models matching the project's search terms (public API, no token)."""
from __future__ import annotations

import requests


def search(queries: list[str]) -> dict:
    out: dict[str, dict] = {"spaces": {}, "models": {}}
    for q in queries:
        for kind in ("spaces", "models"):
            r = requests.get(f"https://huggingface.co/api/{kind}", params={"search": q, "limit": 200, "full": "false"}, timeout=30)
            if not r.ok:
                continue
            for it in r.json():
                out[kind][it["id"]] = {"id": it["id"], "likes": it.get("likes", 0), "createdAt": it.get("createdAt")}
    return {k: list(v.values()) for k, v in out.items()}
