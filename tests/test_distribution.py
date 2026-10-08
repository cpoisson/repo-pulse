from datetime import datetime, timezone

from repo_pulse.collect.distribution import is_binary_asset, release_download_total
from repo_pulse.config import load
from repo_pulse.metrics.adoption import _daily, _snapshot_window
from repo_pulse.metrics.util import Windows


def test_legacy_pypi_becomes_a_channel(tmp_path):
    cfg = tmp_path / "configs" / "x.yaml"
    cfg.parent.mkdir()
    cfg.write_text("repo: a/b\npypi: pkg\ndistribution:\n  - {type: docker, name: a/b}\n")
    c = load(cfg)
    assert c.distribution == [{"type": "pypi", "name": "pkg"}, {"type": "docker", "name": "a/b"}] and c.pypi == "pkg"
    cfg.write_text("repo: a/b\ndistribution:\n  - {type: npm, name: b}\n")
    assert load(cfg).pypi is None


def test_release_totals_skip_checksums_and_signatures():
    rels = [{"assets": [{"name": "beacon-chain-linux-amd64", "downloads": 10}, {"name": "beacon-chain-linux-amd64.sha256", "downloads": 9},
                        {"name": "beacon-chain-linux-amd64.sig", "downloads": 8}]}]
    assert release_download_total(rels) == 10 and not is_binary_asset("checksums.txt")


def test_snapshot_window_needs_a_snapshot_before_the_window():
    w = Windows.of("2026-10-07", 90)
    rows = [{"date": "2026-10-07", "n": 100}]
    assert _snapshot_window(rows, lambda r: r["n"], w)[:2] == (None, None)
    rows = [{"date": "2026-04-01", "n": 10}, {"date": "2026-07-01", "n": 40}, {"date": "2026-10-07", "n": 100}]
    assert _snapshot_window(rows, lambda r: r["n"], w)[:2] == (60, 30)


def test_daily_series_reports_uncovered_prior_window():
    w = Windows.of("2026-10-07", 90)
    by_day = {f"2026-{m:02d}-{d:02d}": 1 for m in range(8, 11) for d in range(1, 29) if f"2026-{m:02d}-{d:02d}" <= "2026-10-07"}
    cur, prior, note, _ = _daily(by_day, w)
    assert prior is None and "partly covered" in note
