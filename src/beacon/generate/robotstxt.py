from __future__ import annotations

from beacon.checks.crawl_policy import AGENT_FETCHERS
from beacon.fetch import Site
from beacon.robots import parse_robots


async def generate_robots_txt(site: Site) -> str | None:
    original = await site.robots_txt()
    sitemap_url = await _sitemap_url(site)
    if original is None:
        lines = ["User-agent: *", "Allow: /", ""]
        if sitemap_url:
            lines += [f"Sitemap: {sitemap_url}", ""]
        return "\n".join(lines)

    robots = parse_robots(original)
    blocked = [agent for agent in AGENT_FETCHERS if robots.blocks_entirely(agent)]
    needs_sitemap = sitemap_url is not None and not robots.sitemaps
    if not blocked and not needs_sitemap:
        return None

    parts: list[str] = []
    for agent in blocked:
        parts += [f"User-agent: {agent}", "Allow: /", ""]
    parts.append(original.rstrip())
    if needs_sitemap:
        parts += ["", f"Sitemap: {sitemap_url}"]
    return "\n".join(parts) + "\n"


async def _sitemap_url(site: Site) -> str | None:
    response = await site.get("/sitemap.xml")
    if response is not None and response.status_code == 200:
        return site.fetcher.url_for("/sitemap.xml")
    return None
