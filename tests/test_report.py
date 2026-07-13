from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.report import render_html
from beacon.scoring import score

FINDINGS = [
    Finding(
        id="agent-fetchers-allowed",
        layer=Layer.CRAWL_POLICY,
        tier=Tier.TODAY,
        status=Status.FAIL,
        weight=3,
        summary="Blocks <agents> & fetchers",
        fix="Unblock them",
        evidence="ChatGPT-User",
    ),
    Finding(
        id="llms-txt",
        layer=Layer.API_MCP,
        tier=Tier.FUTURE,
        status=Status.PASS,
        weight=2,
        summary="llms.txt present",
    ),
]


def test_render_html_is_self_contained_and_escaped():
    html = render_html("shop.example", FINDINGS, score(FINDINGS))
    assert html.startswith("<!doctype html>")
    assert "shop.example" in html
    assert "0/100" in html and "100/100" in html
    assert "Blocks &lt;agents&gt; &amp; fetchers" in html  # summary is escaped
    assert "fix: Unblock them" in html
    assert 'class="tier"' in html  # future finding is tagged
    assert "cdn." not in html and "<script" not in html  # no external assets or JS
