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
def test_batch_parallel_flag(two_domains):
    result = runner.invoke(app, ["audit", "--file", str(two_domains), "--parallel", "1"])
    assert result.exit_code == 0
    assert result.output.splitlines()[0].startswith("rank")
    assert runner.invoke(app, ["audit", "--file", str(two_domains), "--parallel", "0"]).exit_code != 0


@respx.mock
def test_batch_html_benchmark(two_domains, tmp_path):
    out = tmp_path / "benchmark.html"
    result = runner.invoke(app, ["audit", "--file", str(two_domains), "--html", str(out)])
    assert result.exit_code == 0
    assert f"Benchmark HTML written to {out}" in result.output
    html = out.read_text()
    assert "Beacon benchmark" in html
    assert "good.example" in html and "bad.example" in html


@respx.mock
def test_score_prints_bare_number_and_saves(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    mock_domain(GOOD, "User-agent: *\nAllow: /\n")
    result = runner.invoke(app, ["score", "good.example"])
    assert result.exit_code == 0
    assert result.output.strip().isdigit()
    badge = runner.invoke(app, ["badge", "good.example"])
    assert badge.exit_code == 0


@respx.mock
def test_audit_fail_only_hides_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    mock_domain(BAD, "User-agent: *\nDisallow: /\n")
    result = runner.invoke(app, ["audit", "bad.example", "--fail-only"])
    assert result.exit_code == 0
    assert "Agent visibility today" in result.output
    assert "FAIL" in result.output
    assert "PASS" not in result.output
    assert "INFO" not in result.output


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


@respx.mock
def test_watch_once_writes_status_page(two_domains, tmp_path):
    out = tmp_path / "status.html"
    result = runner.invoke(app, ["watch", "--file", str(two_domains), "--once", "--html", str(out)])
    assert result.exit_code == 0
    html = out.read_text(encoding="utf-8")
    assert "Beacon benchmark" in html
    assert "good.example" in html and "bad.example" in html

    single = tmp_path / "single.html"
    runner.invoke(app, ["watch", "good.example", "--once", "--html", str(single)])
    assert "Beacon audit" in single.read_text(encoding="utf-8")


@respx.mock
def test_watch_once_writes_badge(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    mock_domain(GOOD, "User-agent: *\nAllow: /\n")
    out = tmp_path / "badge.json"
    result = runner.invoke(app, ["watch", "good.example", "--once", "--badge", str(out)])
    assert result.exit_code == 0
    badge = json.loads(out.read_text(encoding="utf-8"))
    assert badge["label"] == "agent visibility"
    assert badge["message"].endswith("/100")

    domains = tmp_path / "d.txt"
    domains.write_text("good.example\n")
    rejected = runner.invoke(app, ["watch", "--file", str(domains), "--once", "--badge", str(out)])
    assert rejected.exit_code not in (0, 3)


def test_watch_rejects_bad_interval():
    result = runner.invoke(app, ["watch", "x.example", "--once", "--interval", "soon"])
    assert result.exit_code != 0


@respx.mock
def test_badge_from_recorded_history(two_domains):
    runner.invoke(app, ["audit", "--file", str(two_domains)])
    result = runner.invoke(app, ["badge", "good.example"])
    assert result.exit_code == 0
    badge = json.loads(result.output)
    assert badge["schemaVersion"] == 1
    assert badge["label"] == "agent visibility"
    assert badge["message"].endswith("/100")
    assert badge["color"]


@respx.mock
def test_badge_md_line(two_domains):
    runner.invoke(app, ["audit", "--file", str(two_domains)])
    result = runner.invoke(app, ["badge", "good.example", "--md"])
    assert result.exit_code == 0
    assert result.output.strip() == (
        "![agent visibility](https://img.shields.io/endpoint?url=<BADGE-JSON-URL>)"
    )
    hosted = runner.invoke(
        app, ["badge", "good.example", "--md", "--url", "https://x.example/badge.json"]
    )
    assert "url=https%3A%2F%2Fx.example%2Fbadge.json" in hosted.output
    no_md = runner.invoke(app, ["badge", "good.example", "--url", "https://x.example/b.json"])
    assert no_md.exit_code != 0


def test_badge_needs_history(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    assert runner.invoke(app, ["badge", "never.example"]).exit_code == 2


def test_diff_needs_two_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    result = runner.invoke(app, ["diff", "never-audited.example"])
    assert result.exit_code == 2


@respx.mock
def test_watch_formats_discord_webhook_embeds(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    mock_domain(GOOD, "User-agent: *\nAllow: /\n")
    runner.invoke(app, ["watch", "good.example", "--once"])
    mock_domain(GOOD, "User-agent: *\nDisallow: /\n")
    hook = respx.post("https://discord.com/api/webhooks/123/abc").respond(200)
    third = runner.invoke(
        app,
        ["watch", "good.example", "--once", "--webhook", "https://discord.com/api/webhooks/123/abc"],
    )
    assert third.exit_code == 3
    assert hook.called
    body = json.loads(hook.calls.last.request.content)
    assert "embeds" in body
    assert body["embeds"][0]["title"].startswith("good.example: today")


@respx.mock
def test_watch_formats_slack_webhook_text(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    mock_domain(GOOD, "User-agent: *\nAllow: /\n")
    runner.invoke(app, ["watch", "good.example", "--once"])
    mock_domain(GOOD, "User-agent: *\nDisallow: /\n")
    hook = respx.post("https://hooks.slack.com/services/T00/B00/XYZ").respond(200)
    third = runner.invoke(
        app,
        ["watch", "good.example", "--once", "--webhook", "https://hooks.slack.com/services/T00/B00/XYZ"],
    )
    assert third.exit_code == 3
    assert hook.called
    body = json.loads(hook.calls.last.request.content)
    assert set(body) == {"text"}
    assert "agent-fetchers-allowed: PASS" in body["text"]
