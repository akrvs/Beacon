"""Render an audit as JSON or a human-readable terminal report."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.scoring import ScoreCard

_STATUS_MARK = {
    Status.PASS: "✓ PASS",
    Status.WARN: "! WARN",
    Status.FAIL: "✗ FAIL",
    Status.INFO: "i INFO",
}

_LAYER_TITLE = {
    Layer.CRAWL_POLICY: "Crawl policy",
    Layer.CONTENT: "AI-readable content",
    Layer.API_MCP: "API / MCP availability",
    Layer.CHECKOUT: "Agent checkout readiness",
}


def to_json(domain: str, findings: list[Finding], card: ScoreCard) -> str:
    payload = {
        "domain": domain,
        "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **card.to_dict(),
        "findings": [f.to_dict() for f in findings],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render_text(domain: str, findings: list[Finding], card: ScoreCard) -> str:
    lines = [
        f"Beacon audit — {domain}",
        "=" * (15 + len(domain)),
        "",
        f"Agent visibility today : {_fmt(card.today.percent)}",
        f"Future readiness       : {_fmt(card.future.percent)}",
    ]
    for layer in Layer:
        layer_findings = [f for f in findings if f.layer is layer]
        if not layer_findings:
            continue
        lines += ["", f"{_LAYER_TITLE[layer]}", "-" * len(_LAYER_TITLE[layer])]
        for finding in layer_findings:
            tier_tag = " [future]" if finding.tier is Tier.FUTURE else ""
            lines.append(f"  {_STATUS_MARK[finding.status]}{tier_tag}  {finding.summary}")
            if finding.evidence:
                lines.append(f"           evidence: {finding.evidence}")
            if finding.fix and finding.status in (Status.WARN, Status.FAIL):
                lines.append(f"           fix: {finding.fix}")
    fixes = [f for f in findings if f.fix and f.status in (Status.WARN, Status.FAIL)]
    if fixes:
        lines += ["", f"{len(fixes)} concrete fix(es) listed above."]
    return "\n".join(lines)


def _fmt(percent: int | None) -> str:
    return f"{percent}/100" if percent is not None else "n/a (no checks in this tier yet)"
