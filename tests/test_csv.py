import respx
from typer.testing import CliRunner

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.cli import app
from beacon.report import render_csv, render_ranking_csv
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
            summary='blocked, "fetchers"',
            fix="Unblock them",
        ),
    ]


def test_render_csv_rows():
    findings = findings_sample()
    text = render_csv("shop.example", findings, score(findings))
    lines = text.splitlines()
    assert lines[0] == "domain,layer,id,status,tier,summary,fix"
    assert lines[1] == "shop.example,crawl_policy,robots-txt-present,pass,today,robots.txt is present,"
    assert lines[2] == 'shop.example,crawl_policy,agent-fetchers-allowed,fail,today,"blocked, ""fetchers""",Unblock them'


def test_render_ranking_csv():
    findings = findings_sample()
    text = render_ranking_csv([("a.example", findings, score(findings)), ("b.example", [], score([]))])
    lines = text.splitlines()
    assert lines[0] == "rank,domain,today,future,fixes"
    assert lines[1].startswith("1,a.example,")
    assert lines[2] == "2,b.example,,,0"


@respx.mock
def test_audit_csv_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path / "home"))
    respx.get(f"{GOOD}/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
    respx.get(url__startswith=GOOD).respond(404)
    out = tmp_path / "report.csv"
    result = runner.invoke(app, ["audit", "good.example", "--csv", str(out)])
    assert result.exit_code == 0
    assert f"CSV report written to {out}" in result.output
    text = out.read_text(encoding="utf-8")
    assert text.startswith("domain,layer,id,status,tier,summary,fix")
    assert "good.example" in text

    domains = tmp_path / "domains.txt"
    domains.write_text("good.example\n")
    ranking = tmp_path / "ranking.csv"
    result = runner.invoke(app, ["audit", "--file", str(domains), "--csv", str(ranking)])
    assert result.exit_code == 0
    assert ranking.read_text(encoding="utf-8").startswith("rank,domain,today,future,fixes")
