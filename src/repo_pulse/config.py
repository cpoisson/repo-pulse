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


FORGES = {"github": ("GitHub", "github.com"), "gitlab": ("GitLab", "gitlab.com")}
# Distribution channels with public download counts; `name` is the package/image (github_releases needs none).
CHANNELS = {"pypi": "PyPI", "npm": "npm", "crates": "crates.io", "docker": "Docker Hub", "github_releases": "GitHub release assets"}
# What a changed file is; only `code` counts toward bus factor and code concentration, generated/deps count for nobody.
PATH_KINDS = ("code", "tests", "docs", "build", "deps", "generated")


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
    forge: str = "github"                    # github | gitlab (gitlab.com): where issues, PRs/MRs and CI come from
    distribution: list[dict] = field(default_factory=list)   # [{type, name}] channels users install from (CHANNELS)
    path_kinds: dict[str, str] = field(default_factory=dict)  # path prefix or glob -> one of PATH_KINDS, before defaults
    changelog_fragments: str | None = None   # dir where each PR adds a changelog fragment (Added/Fixed/... or towncrier)

    @property
    def owner(self) -> str:
        return self.repo.rsplit("/", 1)[0]   # GitLab namespaces can nest: group/subgroup/project

    @property
    def name(self) -> str:
        return self.repo.rsplit("/", 1)[1]

    @property
    def forge_name(self) -> str:
        return FORGES[self.forge][0]

    @property
    def web_url(self) -> str:
        return f"https://{FORGES[self.forge][1]}/{self.repo}"

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
    dist = _distribution(raw)
    return Config(
        path=path,
        repo=raw["repo"],
        title=raw.get("title", raw["repo"]),
        local_clone=_clone_path(raw.get("local_clone"), raw["repo"], path),
        pypi=raw.get("pypi") or next((d["name"] for d in dist if d["type"] == "pypi"), None),
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
        forge=_forge(raw.get("forge")),
        distribution=dist,
        path_kinds=_path_kinds(raw.get("path_kinds")),
        changelog_fragments=raw.get("changelog_fragments"),
    )


def _distribution(raw: dict) -> list[dict]:
    """`distribution` entries, plus the legacy top-level `pypi:` shorthand as a PyPI channel."""
    dist = [dict(d) for d in raw.get("distribution") or []]
    for d in dist:
        if d.get("type") not in CHANNELS:
            raise ValueError(f"distribution type must be one of {', '.join(CHANNELS)}, got {d.get('type')!r}")
        if d["type"] != "github_releases" and not d.get("name"):
            raise ValueError(f"distribution entry {d} needs a name")
    if raw.get("pypi") and not any(d["type"] == "pypi" for d in dist):
        dist.insert(0, {"type": "pypi", "name": raw["pypi"]})
    return dist


def _path_kinds(raw: dict | None) -> dict[str, str]:
    for pat, kind in (raw or {}).items():
        if kind not in PATH_KINDS:
            raise ValueError(f"path_kinds[{pat!r}] must be one of {', '.join(PATH_KINDS)}, got {kind!r}")
    return dict(raw or {})


def _forge(raw: str | None) -> str:
    forge = str(raw or "github").lower()
    if forge not in FORGES:
        raise ValueError(f"forge must be one of {', '.join(FORGES)}, got {raw!r}")
    return forge
