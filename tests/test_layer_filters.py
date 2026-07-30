import json

import pytest
import respx
from typer.testing import CliRunner

from beacon.cli import app

runner = CliRunner()

GOOD = "https://good.example"


@pytest.fixture
def good_domain(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path / "home"))
    respx.get(f"{GOOD}/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
    respx.get(url__startswith=GOOD).respond(404)


@respx.mock
def test_only_runs_selected_layers(good_domain):
    result = runner.invoke(app, ["audit", "good.example", "--only", "crawl_policy", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert {f["layer"] for f in data["findings"]} == {"crawl_policy"}


@respx.mock
def test_skip_drops_selected_layers(good_domain):
    result = runner.invoke(
        app, ["audit", "good.example", "--skip", "checkout,api_mcp", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    layers = {f["layer"] for f in data["findings"]}
    assert "checkout" not in layers and "api_mcp" not in layers
    assert "crawl_policy" in layers


def test_only_and_skip_are_mutually_exclusive():
    result = runner.invoke(
        app, ["audit", "good.example", "--only", "content", "--skip", "checkout"]
    )
    assert result.exit_code != 0


def test_unknown_layer_rejected():
    result = runner.invoke(app, ["audit", "good.example", "--only", "nonsense"])
    assert result.exit_code != 0
    assert "valid layers" in result.output


def test_skipping_everything_rejected():
    result = runner.invoke(
        app,
        ["audit", "good.example", "--skip", "crawl_policy,content,api_mcp,checkout"],
    )
    assert result.exit_code != 0
