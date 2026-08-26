"""YAML-authored checks from $BEACON_HOME/checks join every audit."""

import asyncio
import textwrap

from beacon.checks import ALL_CHECKS, BUILTIN_CHECKS
from beacon.checks.custom import CustomCheck, load_custom_checks

SPEC = {
    "id": "partner-api",
    "layer": "api_mcp",
    "weight": 2,
    "on_fail": "warn",
    "probes": [
        {"path": "/api/status", "expect_status": 200, "text_contains": ["ok"]},
        {"path": "/health", "header_exists": "x-build"},
    ],
}


class StubResponse:
    def __init__(self, status=200, text="", headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}


class StubSite:
    def __init__(self, responses):
        self.responses = responses

    async def get(self, path):
        return self.responses.get(path)


def test_passing_probes_emit_pass_finding():
    site = StubSite(
        {
            "/api/status": StubResponse(text='{"status":"ok"}'),
            "/health": StubResponse(headers={"X-Build": "42"}),
        }
    )
    findings = asyncio.run(CustomCheck(SPEC).run(site))
    assert len(findings) == 1
    assert findings[0].status.value == "pass"
    assert findings[0].weight == 2
    assert "2 probe(s)" in findings[0].summary


def test_failed_assertions_report_configured_severity():
    site = StubSite(
        {
            "/api/status": StubResponse(status=500),
            "/health": StubResponse(headers={}),
        }
    )
    findings = asyncio.run(CustomCheck(SPEC).run(site))
    assert findings[0].status.value == "warn"
    assert "failed 2 assertion(s)" in findings[0].summary
    assert "/api/status: HTTP 500, wanted 200" in findings[0].evidence
    assert "/health: missing header x-build" in findings[0].evidence


def test_probe_without_response_is_unreachable():
    site = StubSite({})
    findings = asyncio.run(CustomCheck(SPEC).run(site))
    assert findings[0].status.value == "warn"
    assert "unreachable" in findings[0].evidence


def test_check_without_probes_is_rejected():
    try:
        CustomCheck({"id": "empty", "layer": "content", "probes": []})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for missing probes")


def test_load_skips_broken_files(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    checks_dir = tmp_path / "checks"
    checks_dir.mkdir()
    (checks_dir / "broken.yaml").write_text("checks: [ {id: no-probes} ]", encoding="utf-8")
    (checks_dir / "garbage.yaml").write_text("\t\t::not::yaml:", encoding="utf-8")

    assert load_custom_checks() == []
    assert len(ALL_CHECKS) >= len(BUILTIN_CHECKS)


def test_load_reads_valid_files(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    checks_dir = tmp_path / "checks"
    checks_dir.mkdir()
    (checks_dir / "partner.yaml").write_text(
        textwrap.dedent(
            """
            checks:
              - id: partner-api
                layer: api_mcp
                probes:
                  - path: /api/status
                    expect_status: 200
                  - path: /api/status
                    expect_status: 200
                    text_contains: ["ok"]
                    header_exists: x-build
            """
        ),
        encoding="utf-8",
    )
    checks = load_custom_checks()
    assert [c.id for c in checks] == ["partner-api"]
    assert len(checks[0].probes) == 2
