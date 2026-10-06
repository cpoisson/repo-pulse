from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def default_clone(repo: str) -> Path:
    """Shared shallow-clone location; REPO_PULSE_CLONES (env or .env, read lazily) moves it per machine."""
    return Path(os.environ.get("REPO_PULSE_CLONES", "~/.cache/repo-pulse/clones")).expanduser() / repo.replace("/", "__")


def _clone_path(raw: str | None, repo: str, config_path: Path) -> Path:
    """Optional `local_clone` override (env vars and ~ expanded, relative to the repo root); else the shared clone dir."""
    if not raw:
        return default_clone(repo)
    p = Path(os.path.expandvars(raw)).expanduser()
    return p if p.is_absolute() else (config_path.parent.parent / p).resolve()


@dataclass
class Config:
    path: Path
    repo: str
    title: str
    local_clone: Path
    pypi: str | None
    window_days: int
    maintainers: list[str]
    bots: list[str]
    modules: dict[str, str]
    module_test_keywords: dict[str, list[str]]
    critical_dependencies: list[str]
    known_incidents: list[dict]
    hf_hub_queries: list[str]
    issue_types: dict[str, str]
    themes: dict[str, str]
    thresholds: dict[str, dict]
    classifier_gate: dict = field(default_factory=dict)
    star_history_svg: str | None = None
    ci_workflow: str | None = None           # Actions workflow name used for CI KPIs; default: most frequent on push
    backend_registry: dict | None = None     # optional {path, pattern}: regex with one group = backend id
    classifier: str = "local"                # local (free, default) | auto (best measured, incl. API) | jev (force Jev)

    @property
    def owner(self) -> str:
        return self.repo.split("/")[0]

    @property
    def name(self) -> str:
        return self.repo.split("/")[1]

    @property
    def slug(self) -> str:
        return self.repo.replace("/", "__")

    def module_for(self, path: str) -> str:
        for prefix, mod in self.modules.items():
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                return mod
        return "other"

    def is_bot(self, login: str | None) -> bool:
        return not login or login in self.bots or login.endswith("[bot]")


def load(path: str | Path) -> Config:
    path = Path(path).resolve()
    raw = yaml.safe_load(path.read_text())
    return Config(
        path=path,
        repo=raw["repo"],
        title=raw.get("title", raw["repo"]),
        local_clone=_clone_path(raw.get("local_clone"), raw["repo"], path),
        pypi=raw.get("pypi"),
        window_days=int(raw.get("window_days", 90)),
        maintainers=raw.get("maintainers") or [],
        bots=raw.get("bots") or [],
        modules=raw.get("modules") or {},
        module_test_keywords=raw.get("module_test_keywords") or {},
        critical_dependencies=raw.get("critical_dependencies") or [],
        known_incidents=raw.get("known_incidents") or [],
        hf_hub_queries=raw.get("hf_hub_queries") or [],
        issue_types=raw.get("issue_types") or {},
        themes=raw.get("themes") or {},
        thresholds=raw.get("thresholds") or {},
        classifier_gate=raw.get("classifier_gate") or {},
        star_history_svg=raw.get("star_history_svg"),
        ci_workflow=raw.get("ci_workflow"),
        backend_registry=raw.get("backend_registry"),
        classifier=str(raw.get("classifier") or "local"),
    )
