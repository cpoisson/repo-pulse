import subprocess

from repo_pulse.collect.git_local import changelog_entries
from repo_pulse.metrics.code import new_path, path_kind, work


def test_path_kinds():
    assert path_kind("beacon-chain/blockchain/log.go") == "code"
    assert path_kind("beacon-chain/blockchain/log_test.go") == "tests"
    assert path_kind("tests/test_trainer.py") == "tests"
    assert path_kind("docs/source/index.md") == "docs"
    assert path_kind("README.md") == "docs"
    assert path_kind(".github/workflows/tests.yml") == "build"
    assert path_kind("tools/BUILD.bazel") == "build"
    assert path_kind("uv.lock") == "deps"
    assert path_kind("proto/eth/v1/beacon.pb.go") == "generated"
    assert path_kind("api/log.go", generated={"api/log.go"}) == "generated"
    assert path_kind("api/x_mock.go", gen_globs=("*_mock.go",)) == "generated"
    assert path_kind("scripts/release.sh", {"scripts/": "build"}) == "build"


def test_rename_paths_keep_new_name():
    assert new_path("src/{old => new}/a.py") == "src/new/a.py"
    assert new_path("src/{ => sub}/a.py") == "src/sub/a.py"
    assert new_path("a.py => b.py") == "b.py"


def test_work_grows_sublinearly():
    small, big = work(35), work(1350)
    assert work(0) == 0 and 1.5 < big / small < 2.5


def test_changelog_sections_and_towncrier(tmp_path):
    git = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True, text=True).stdout
    git("init", "-q", "-b", "main")
    git("config", "user.email", "a@b.c"); git("config", "user.name", "A")
    (tmp_path / "changelog").mkdir()
    (tmp_path / "changelog" / "a_metrics.md").write_text("### Added\n\n- metrics\n\n### Fixed\n\n- bug\n")
    git("add", "."); git("commit", "-q", "-m", "one")
    (tmp_path / "changelog" / "123.bugfix.md").write_text("Fix a crash.\n")
    git("add", "."); git("commit", "-q", "-m", "two")
    two, one = git("log", "--format=%H").split()
    assert changelog_entries(tmp_path, "changelog/", ref="HEAD") == {one: ["added", "fixed"], two: ["bugfix"]}


def test_pr_type():
    from repo_pulse.metrics.code import pr_type
    code = {"files": [{"path": "beacon-chain/sync/a.go"}, {"path": "changelog/x.md"}]}
    assert pr_type(code, path_kind, ["added", "fixed"]) == "feature"
    assert pr_type(code, path_kind, ["removed"]) == "change"
    assert pr_type(code, path_kind, ["ignored"]) == "internal"
    assert pr_type(code, path_kind, None) == "untyped"
    assert pr_type({"files": [{"path": "README.md"}, {"path": ".github/workflows/ci.yml"}]}, path_kind, ["added"]) == "no_code"
    assert pr_type({"files": []}, path_kind, None) == "untyped"
