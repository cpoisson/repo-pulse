import dataclasses
import re
from pathlib import Path

import yaml

from repo_pulse.config import Config, load

CONFIGS = Path(__file__).parent.parent / "configs"


def test_template_documents_every_field():
    text = (CONFIGS / "_template.yaml").read_text()
    documented = set(yaml.safe_load(text)) | set(re.findall(r"^# (\w+):", text, re.M))
    assert {f.name for f in dataclasses.fields(Config)} - {"path"} <= documented


def test_clone_defaults_to_shared_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("REPO_PULSE_CLONES", str(tmp_path))
    assert load(CONFIGS / "_template.yaml").local_clone == tmp_path / "OWNER__NAME"


def test_clone_override_expands_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SRC", str(tmp_path))
    cfg = tmp_path / "configs" / "x.yaml"
    cfg.parent.mkdir()
    cfg.write_text("repo: a/b\nlocal_clone: $SRC/b\n")
    assert load(cfg).local_clone == tmp_path / "b"


def test_forge_defaults_to_github_and_accepts_gitlab(tmp_path):
    cfg = tmp_path / "configs" / "x.yaml"
    cfg.parent.mkdir()
    cfg.write_text("repo: a/b\n")
    assert load(cfg).web_url == "https://github.com/a/b"
    cfg.write_text("repo: grp/sub/proj\nforge: gitlab\n")
    c = load(cfg)
    assert (c.owner, c.name, c.web_url) == ("grp/sub", "proj", "https://gitlab.com/grp/sub/proj")


def test_parse_repo_urls():
    from repo_pulse.init import parse_repo

    assert parse_repo("owner/name") == ("github", "owner/name")
    assert parse_repo("https://github.com/owner/name.git") == ("github", "owner/name")
    assert parse_repo("https://gitlab.com/fdroid/fdroiddata") == ("gitlab", "fdroid/fdroiddata")
    assert parse_repo("gitlab.com/grp/sub/proj/-/issues") == ("gitlab", "grp/sub/proj")
