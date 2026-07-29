import json

import pytest
import respx
from typer.testing import CliRunner

from beacon.cli import app

runner = CliRunner()

GOOD = "https://good.example"
BAD = "https://bad.example"


def mock_domain(base: str, robots: str) -> None:
    respx.get(f"{base}/robots.txt").respond(200, text=robots)
    respx.get(url__startswith=base).respond(404)


@pytest.fixture
def two_domains(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path / "home"))
    mock_domain(GOOD, "User-agent: *\nAllow: /\nSitemap: https://good.example/sm.xml\n")
    mock_domain(BAD, "User-agent: *\nDisallow: /\n")
    domains = tmp_path / "domains.txt"
    domains.write_text("# prospects\ngood.example\n\nbad.example\n")
    return domains


@respx.mock
def test_batch_ranking_and_min_score(two_domains):
    result = runner.invoke(app, ["audit", "--file", str(two_domains), "--min-score", "50"])
    assert result.exit_code == 1
    lines = result.output.splitlines()
    assert lines[0].startswith("rank")
    assert "good.example" in lines[1] and "bad.example" in lines[2]  # ranked
    assert "Below --min-score 50: bad.example" in result.output


@respx.mock
def test_batch_json_and_history(two_domains):
    result = runner.invoke(app, ["audit", "--file", str(two_domains), "--json"])
    assert result.exit_code == 0
    batch = json.loads(result.output)
    assert {entry["domain"] for entry in batch} == {"good.example", "bad.example"}

    runner.invoke(app, ["audit", "--file", str(two_domains)])
    diff_result = runner.invoke(app, ["diff", "good.example"])
    assert diff_result.exit_code == 0
    assert "Beacon diff — good.example" in diff_result.output
    assert "No finding changes" in diff_result.output


@respx.mock
def test_batch_html_benchmark(two_domains, tmp_path):
    out = tmp_path / "benchmark.html"
    result = runner.invoke(app, ["audit", "--file", str(two_domains), "--html", str(out)])
    assert result.exit_code == 0
    assert f"Benchmark HTML written to {out}" in result.output
    html = out.read_text()
    assert "Beacon benchmark" in html
    assert "good.example" in html and "bad.example" in html


def test_domain_and_file_are_mutually_exclusive(tmp_path):
    domains = tmp_path / "d.txt"
    domains.write_text("a.example\n")
    assert runner.invoke(app, ["audit", "x.example", "--file", str(domains)]).exit_code != 0
    assert runner.invoke(app, ["audit"]).exit_code != 0


@respx.mock
def test_watch_once_detects_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    robots = respx.get(f"{GOOD}/robots.txt").respond(
        200, text="User-agent: *\nAllow: /\nSitemap: https://good.example/sm.xml\n"
    )
    respx.get(url__startswith=GOOD).respond(404)
    hook = respx.post("https://hook.example/notify").respond(200)

    first = runner.invoke(app, ["watch", "good.example", "--once"])
    assert first.exit_code == 0
    assert "baseline recorded" in first.output

    second = runner.invoke(app, ["watch", "good.example", "--once"])
    assert second.exit_code == 0
    assert "no changes" in second.output

    robots.respond(200, text="User-agent: *\nDisallow: /\n")
    third = runner.invoke(
        app,
        ["watch", "good.example", "--once", "--webhook", "https://hook.example/notify"],
    )
    assert third.exit_code == 3  # --once signals changes via exit code
    assert "CHANGED" in third.output
    assert "Agent visibility today" in third.output
    assert hook.called
    notification = json.loads(hook.calls.last.request.content)
    assert notification["has_changes"] is True
    assert notification["domain"] == "good.example"
    assert "diff" in notification


def test_watch_rejects_bad_interval():
    result = runner.invoke(app, ["watch", "x.example", "--once", "--interval", "soon"])
    assert result.exit_code != 0


def test_diff_needs_two_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    result = runner.invoke(app, ["diff", "never-audited.example"])
    assert result.exit_code == 2
