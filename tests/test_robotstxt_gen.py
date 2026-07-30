import pytest
import respx

from beacon.checks.crawl_policy import AGENT_FETCHERS
from beacon.fetch import Site
from beacon.generate.robotstxt import generate_robots_txt
from beacon.robots import parse_robots

BASE = "https://shop.example"

SITEMAP = "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'></urlset>"


async def generate(robots_status: int, robots_text: str = "", sitemap_status: int = 404) -> str | None:
    respx.get(f"{BASE}/robots.txt").respond(robots_status, text=robots_text)
    respx.get(f"{BASE}/sitemap.xml").respond(sitemap_status, text=SITEMAP)
    site = Site("shop.example")
    try:
        return await generate_robots_txt(site)
    finally:
        await site.aclose()


@respx.mock
@pytest.mark.asyncio
async def test_fresh_file_when_robots_missing():
    text = await generate(404, sitemap_status=200)
    assert text is not None
    assert "User-agent: *" in text
    assert "Allow: /" in text
    assert f"Sitemap: {BASE}/sitemap.xml" in text


@respx.mock
@pytest.mark.asyncio
async def test_unblocks_agent_fetchers_and_keeps_original():
    original = "User-agent: ChatGPT-User\nDisallow: /\n\nUser-agent: *\nDisallow: /admin\n"
    text = await generate(200, original, sitemap_status=200)
    assert text is not None
    assert "Disallow: /admin" in text
    fixed = parse_robots(text)
    for agent in AGENT_FETCHERS:
        assert not fixed.blocks_entirely(agent)
    assert f"Sitemap: {BASE}/sitemap.xml" in text


@respx.mock
@pytest.mark.asyncio
async def test_wildcard_block_is_lifted_for_fetchers():
    text = await generate(200, "User-agent: *\nDisallow: /\n")
    assert text is not None
    fixed = parse_robots(text)
    for agent in AGENT_FETCHERS:
        assert not fixed.blocks_entirely(agent)
    assert fixed.blocks_entirely("SomeOtherBot")


@respx.mock
@pytest.mark.asyncio
async def test_nothing_to_fix_returns_none():
    text = await generate(200, f"User-agent: *\nAllow: /\nSitemap: {BASE}/sm.xml\n")
    assert text is None


@respx.mock
@pytest.mark.asyncio
async def test_declared_sitemap_not_duplicated():
    text = await generate(
        200,
        f"User-agent: GPTBot\nDisallow: /\n\nUser-agent: ChatGPT-User\nDisallow: /\nSitemap: {BASE}/sm.xml\n",
        sitemap_status=200,
    )
    assert text is not None
    assert text.count("Sitemap:") == 1
    fixed = parse_robots(text)
    assert not fixed.blocks_entirely("ChatGPT-User")
    assert fixed.blocks_entirely("GPTBot")
