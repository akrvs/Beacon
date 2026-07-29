import httpx
import respx

from beacon.discover import crawlable_urls
from beacon.fetch import Fetcher, Site
from beacon.robots import parse_robots

BASE = "https://shop.example"


class TestAllows:
    def test_longest_match_wins(self):
        robots = parse_robots("User-agent: *\nDisallow: /shop\nAllow: /shop/public\n")
        assert not robots.allows("beaconbot", "/shop/private")
        assert robots.allows("beaconbot", "/shop/public/item")
        assert robots.allows("beaconbot", "/other")

    def test_wildcard_and_end_anchor(self):
        robots = parse_robots("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*/x\n")
        assert not robots.allows("beaconbot", "/docs/file.pdf")
        assert robots.allows("beaconbot", "/docs/file.pdf.html")
        assert not robots.allows("beaconbot", "/tmp123/x")

    def test_allow_wins_ties(self):
        robots = parse_robots("User-agent: *\nDisallow: /a\nAllow: /a\n")
        assert robots.allows("beaconbot", "/a/b")

    def test_unmatched_agent_is_allowed(self):
        robots = parse_robots("User-agent: other\nDisallow: /\n")
        assert robots.allows("beaconbot", "/anything")

    def test_empty_disallow_allows_everything(self):
        robots = parse_robots("User-agent: *\nDisallow:\n")
        assert robots.allows("beaconbot", "/x")


@respx.mock
async def test_crawlable_urls_respects_robots():
    respx.get(f"{BASE}/robots.txt").respond(
        200, text=f"User-agent: *\nDisallow: /private/\n\nSitemap: {BASE}/sitemap.xml\n"
    )
    respx.get(f"{BASE}/sitemap.xml").respond(
        200,
        text=f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{BASE}/private/secret</loc></url>
  <url><loc>{BASE}/public/page</loc></url>
</urlset>""",
    )
    respx.get(url__startswith=BASE).respond(404)
    site = Site(BASE, fetcher=Fetcher(BASE, client=httpx.AsyncClient(follow_redirects=True)))
    urls = await crawlable_urls(site)
    await site.aclose()
    assert urls == [f"{BASE}/public/page"]
