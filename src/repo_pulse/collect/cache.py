"""Raw-data cache: data/raw/<repo-slug>/<as-of>/<name>.json. Reruns on the same day are free."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

ROOT = Path("data/raw")


def cached(slug: str, as_of: str, name: str, fetch: Callable[[], Any], refresh: bool = False) -> Any:
    path = ROOT / slug / as_of / f"{name}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, default=str))
    return data


def load_all(slug: str, as_of: str) -> dict[str, Any]:
    d = ROOT / slug / as_of
    if not d.exists():
        raise FileNotFoundError(f"No raw data at {d}; run `repo-pulse collect` first")
    return {p.stem: json.loads(p.read_text()) for p in sorted(d.glob("*.json"))}
