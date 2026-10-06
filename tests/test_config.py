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
