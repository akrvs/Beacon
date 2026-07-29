import httpx
import respx

from beacon.checks.base import Status, Tier
from beacon.checks.crawl_policy import CrawlPolicyCheck, parse_robots
from beacon.fetch import Fetcher, Site

BASE = "https://shop.example"


def make_site() -> Site:
    client = httpx.AsyncClient(follow_redirects=True)
    return Site(BASE, fetcher=Fetcher(BASE, client=client))


def by_id(findings, finding_id):
    return next(f for f in findings if f.id == finding_id)


class TestParseRobots:
    def test_groups_and_sitemaps(self):
        robots = parse_robots(
            "User-agent: GPTBot\n"
            "User-agent: ClaudeBot\n"
            "Disallow: /\n"
            "\n"
            "User-agent: *\n"
            "Disallow: /admin\n"
            "Allow: /\n"
            "Sitemap: https://shop.example/sitemap.xml\n"
        )
        assert robots.sitemaps == ["https://shop.example/sitemap.xml"]
        assert robots.blocks_entirely("GPTBot")
        assert robots.blocks_entirely("claudebot")
        assert not robots.blocks_entirely("ChatGPT-User")

    def test_specific_group_overrides_wildcard(self):
        robots = parse_robots(
            "User-agent: *\nDisallow: /\n\nUser-agent: PerplexityBot\nDisallow:\n"
        )
        assert robots.blocks_entirely("Amazonbot")
        assert not robots.blocks_entirely("PerplexityBot")

    def test_comments_and_blank_lines_ignored(self):
        robots = parse_robots("# policy\nUser-agent: * # all\nDisallow: /private\n")
        assert not robots.blocks_entirely("GPTBot")


@respx.mock
async def test_missing_robots_txt_warns():
    respx.get(f"{BASE}/robots.txt").respond(404)
    respx.get(f"{BASE}/sitemap.xml").respond(404)
    site = make_site()
    findings = await CrawlPolicyCheck().run(site)
    await site.aclose()
    assert by_id(findings, "robots-txt-present").status is Status.WARN
    assert by_id(findings, "sitemap-available").status is Status.FAIL


@respx.mock
async def test_blocked_agent_fetchers_fail():
    respx.get(f"{BASE}/robots.txt").respond(
        200, text="User-agent: ChatGPT-User\nUser-agent: Claude-User\nDisallow: /\n"
    )
    respx.get(f"{BASE}/sitemap.xml").respond(200, text="<urlset/>")
    site = make_site()
    findings = await CrawlPolicyCheck().run(site)
    await site.aclose()
    fetchers = by_id(findings, "agent-fetchers-allowed")
    assert fetchers.status is Status.FAIL
    assert "ChatGPT-User" in fetchers.evidence and "Claude-User" in fetchers.evidence
    assert by_id(findings, "sitemap-available").status is Status.WARN


@respx.mock
async def test_training_block_is_info_not_fail():
    respx.get(f"{BASE}/robots.txt").respond(
        200,
        text=(
            "User-agent: GPTBot\nDisallow: /\n\n"
            "Sitemap: https://shop.example/sitemap.xml\n"
        ),
    )
    respx.get(f"{BASE}/sitemap.xml").respond(404)
    site = make_site()
    findings = await CrawlPolicyCheck().run(site)
    await site.aclose()
    assert by_id(findings, "agent-fetchers-allowed").status is Status.PASS
    assert by_id(findings, "training-crawlers-blocked").status is Status.INFO
    assert by_id(findings, "sitemap-available").status is Status.PASS
    assert all(f.tier is Tier.TODAY for f in findings)


def sitemap_with_lastmod(lastmod: str | None) -> str:
    stamp = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{BASE}/page</loc>{stamp}</url></urlset>"
    )


async def freshness_finding(lastmod: str | None):
    respx.get(f"{BASE}/robots.txt").respond(200, text=f"Sitemap: {BASE}/sitemap.xml\n")
    respx.get(f"{BASE}/sitemap.xml").respond(200, text=sitemap_with_lastmod(lastmod))
    site = make_site()
    findings = await CrawlPolicyCheck().run(site)
    await site.aclose()
    return by_id(findings, "sitemap-freshness")


@respx.mock
async def test_fresh_sitemap_passes():
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    finding = await freshness_finding(today)
    assert finding.status is Status.PASS


@respx.mock
async def test_stale_sitemap_warns():
    finding = await freshness_finding("2020-01-01T00:00:00+00:00")
    assert finding.status is Status.WARN
    assert "unmaintained" in finding.summary


@respx.mock
async def test_sitemap_without_lastmod_is_info():
    finding = await freshness_finding(None)
    assert finding.status is Status.INFO
    assert finding.weight == 0


@respx.mock
async def test_no_sitemap_means_no_freshness_finding():
    respx.get(f"{BASE}/robots.txt").respond(404)
    respx.get(f"{BASE}/sitemap.xml").respond(404)
    site = make_site()
    findings = await CrawlPolicyCheck().run(site)
    await site.aclose()
    assert not any(f.id == "sitemap-freshness" for f in findings)
