import json

import pytest
import respx
from typer.testing import CliRunner

from beacon.cli import app
from beacon.config import load_config

runner = CliRunner()

GOOD = "https://good.example"


@pytest.fixture
def good_domain(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    respx.get(f"{GOOD}/robots.txt").respond(200, text="User-agent: *\nDisallow: /\n")
    respx.get(url__startswith=GOOD).respond(404)
    return tmp_path


@respx.mock
def test_audit_reads_min_score_and_layers_from_config(good_domain):
    (good_domain / "beacon.toml").write_text(
        '[audit]\nmin_score = 90\nonly = "crawl_policy"\n', encoding="utf-8"
    )
    result = runner.invoke(app, ["audit", "good.example", "--json"])
    assert result.exit_code == 1
    assert "below --min-score 90" in result.output
    data = json.loads(result.output.split("\nScore ")[0])
    assert {f["layer"] for f in data["findings"]} == {"crawl_policy"}


@respx.mock
def test_cli_flags_override_config(good_domain):
    (good_domain / "beacon.toml").write_text("[audit]\nmin_score = 90\n", encoding="utf-8")
    result = runner.invoke(app, ["audit", "good.example", "--min-score", "0"])
    assert result.exit_code == 0


@respx.mock
def test_watch_reads_interval_and_webhook_from_config(good_domain):
    (good_domain / "beacon.toml").write_text(
        '[watch]\ninterval = "1h"\nwebhook = "https://hook.example/notify"\n', encoding="utf-8"
    )
    hook = respx.post("https://hook.example/notify").respond(200)
    runner.invoke(app, ["watch", "good.example", "--once"])
    respx.get(f"{GOOD}/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
    result = runner.invoke(app, ["watch", "good.example", "--once"])
    assert result.exit_code == 3
    assert hook.called


def test_config_from_beacon_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("BEACON_HOME", str(home))
    monkeypatch.chdir(tmp_path)
    (home / "beacon.toml").write_text("[audit]\nmin_score = 42\n", encoding="utf-8")
    assert load_config()["audit"]["min_score"] == 42


def test_cwd_config_wins_over_beacon_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("BEACON_HOME", str(home))
    monkeypatch.chdir(tmp_path)
    (home / "beacon.toml").write_text("[audit]\nmin_score = 42\n", encoding="utf-8")
    (tmp_path / "beacon.toml").write_text("[audit]\nmin_score = 7\n", encoding="utf-8")
    assert load_config()["audit"]["min_score"] == 7


def test_invalid_toml_is_a_clean_error(good_domain):
    (good_domain / "beacon.toml").write_text("not toml [", encoding="utf-8")
    result = runner.invoke(app, ["audit", "good.example"])
    assert result.exit_code != 0
    assert "not valid TOML" in result.output
