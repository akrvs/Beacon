from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.report import render_benchmark_html, render_html
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


def _finding(fid: str, status: Status, layer: Layer = Layer.CRAWL_POLICY) -> Finding:
    return Finding(
        id=fid, layer=layer, tier=Tier.TODAY, status=status, weight=2,
        summary=f"{fid} summary", fix="do it" if status is not Status.PASS else "",
    )


def test_render_benchmark_html_ranks_and_compares():
    winner = [_finding("robots-ok", Status.PASS), _finding("sitemap", Status.PASS)]
    loser = [_finding("robots-ok", Status.FAIL), _finding("extra-check", Status.WARN)]
    html = render_benchmark_html(
        [
            ("winner.example", winner, score(winner)),
            ("loser.example", loser, score(loser)),
        ]
    )
    assert html.startswith("<!doctype html>")
    assert "leader: winner.example" in html
    assert html.index("winner.example") < html.index("loser.example")  # rank order kept
    assert 'class="leader"' in html
    assert "robots-ok" in html and "extra-check" in html  # matrix is the union of checks
    assert html.count('class="na"') == 2  # sitemap missing for loser, extra-check for winner
    assert "cdn." not in html and "<script" not in html
