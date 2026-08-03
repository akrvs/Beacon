import pytest
import respx
from typer.testing import CliRunner

from beacon.cli import app

runner = CliRunner()

GOOD = "https://good.example"
BAD = "https://bad.example"


@pytest.fixture
def two_domains(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path / "home"))
    respx.get(f"{GOOD}/robots.txt").respond(
        200, text="User-agent: *\nAllow: /\nSitemap: https://good.example/sm.xml\n"
    )
    respx.get(url__startswith=GOOD).respond(404)
    respx.get(f"{BAD}/robots.txt").respond(200, text="User-agent: *\nDisallow: /\n")
    respx.get(url__startswith=BAD).respond(404)


@respx.mock
def test_compare_head_to_head(two_domains):
    result = runner.invoke(app, ["compare", "good.example", "bad.example"])
    assert result.exit_code == 0
    out = result.output
    assert "Beacon compare — good.example vs bad.example" in out
    assert "Agent visibility today" in out
    assert "agent-fetchers-allowed" in out
    assert "<- good.example" in out
    assert "good.example leads on" in out


@respx.mock
def test_compare_html_report(two_domains, tmp_path):
    out = tmp_path / "versus.html"
    result = runner.invoke(app, ["compare", "bad.example", "good.example", "--html", str(out)])
    assert result.exit_code == 0
    assert f"HTML comparison written to {out}" in result.output
    html = out.read_text(encoding="utf-8")
    assert "good.example" in html and "bad.example" in html
    assert "leader: good.example" in html


@respx.mock
def test_compare_saves_history(two_domains):
    runner.invoke(app, ["compare", "good.example", "bad.example"])
    diff = runner.invoke(app, ["diff", "good.example"])
    assert diff.exit_code == 2
    runner.invoke(app, ["compare", "good.example", "bad.example"])
    diff = runner.invoke(app, ["diff", "good.example"])
    assert diff.exit_code == 0
