import pytest
import respx
from typer.testing import CliRunner

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.cli import app
from beacon.report import render_markdown, render_ranking_markdown
from beacon.scoring import score

runner = CliRunner()

GOOD = "https://good.example"


def findings_sample():
    return [
        Finding(
            id="robots-txt-present",
            layer=Layer.CRAWL_POLICY,
            tier=Tier.TODAY,
            status=Status.PASS,
            weight=1,
            summary="robots.txt is present",
        ),
        Finding(
            id="agent-fetchers-allowed",
            layer=Layer.CRAWL_POLICY,
            tier=Tier.TODAY,
            status=Status.FAIL,
            weight=3,
            summary="blocked | fetchers",
            fix="Unblock them",
            evidence="ChatGPT-User",
        ),
        Finding(
            id="llms-txt",
            layer=Layer.API_MCP,
            tier=Tier.FUTURE,
            status=Status.WARN,
            weight=1,
            summary="No llms.txt",
            fix="Add one",
        ),
    ]


def test_render_markdown_tables():
    findings = findings_sample()
    text = render_markdown("shop.example", findings, score(findings))
    assert text.startswith("# Beacon audit — shop.example")
    assert "## Crawl policy" in text
    assert "| Status | Check | Summary | Fix |" in text
    assert "| FAIL | agent-fetchers-allowed | blocked \\| fetchers — evidence: ChatGPT-User | Unblock them |" in text
    assert "WARN (future)" in text
    assert "| PASS | robots-txt-present | robots.txt is present |  |" in text


def test_render_ranking_markdown():
    findings = findings_sample()
    card = score(findings)
    text = render_ranking_markdown([("a.example", findings, card), ("b.example", [], score([]))])
    assert "# Beacon benchmark — 2 domains" in text
    assert "| 1 | a.example |" in text
    assert "| 2 | b.example |" in text


@respx.mock
def test_audit_md_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path / "home"))
    respx.get(f"{GOOD}/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
    respx.get(url__startswith=GOOD).respond(404)
    out = tmp_path / "report.md"
    result = runner.invoke(app, ["audit", "good.example", "--md", str(out)])
    assert result.exit_code == 0
    assert f"Markdown report written to {out}" in result.output
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Beacon audit — good.example")

    domains = tmp_path / "domains.txt"
    domains.write_text("good.example\n")
    ranking = tmp_path / "ranking.md"
    result = runner.invoke(app, ["audit", "--file", str(domains), "--md", str(ranking)])
    assert result.exit_code == 0
    assert "# Beacon benchmark — 1 domains" in ranking.read_text(encoding="utf-8")
