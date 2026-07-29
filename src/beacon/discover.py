"""Shared page discovery: sitemap URLs and same-domain homepage links."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import httpx
from selectolax.parser import HTMLParser

from beacon.checks.crawl_policy import parse_robots
from beacon.fetch import Site

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


MAX_INDEX_CHILDREN = 4


async def sitemap_urls(site: Site) -> list[str]:
    """URLs from the site's sitemap (robots.txt-declared first, /sitemap.xml
    fallback). For a sitemap index, the first few children are fetched in
    parallel and concatenated, so e.g. Shopify's separate products/pages/
    collections child sitemaps all contribute."""
    async for root in _sitemap_roots(site):
        if root.tag.endswith("sitemapindex"):
            nested = _locs(root, "sm:sitemap/sm:loc")
            children = await asyncio.gather(
                *(_fetch_xml(site, child_url) for child_url in nested[:MAX_INDEX_CHILDREN])
            )
            urls = [
                loc
                for child in children
                if child is not None
                for loc in _locs(child, "sm:url/sm:loc")
            ]
        else:
            urls = _locs(root, "sm:url/sm:loc")
        if urls:
            return urls
    return []


async def sitemap_index_children(site: Site) -> list[str]:
    """Child sitemap URLs when the site's sitemap is an index, else []."""
    async for root in _sitemap_roots(site):
        if root.tag.endswith("sitemapindex"):
            return _locs(root, "sm:sitemap/sm:loc")
        return []
    return []


async def _sitemap_roots(site: Site):
    """Parsed roots of the site's sitemap candidates, best candidate first."""
    robots_text = await site.robots_txt()
    candidates = parse_robots(robots_text).sitemaps if robots_text else []
    candidates.append(site.fetcher.url_for("/sitemap.xml"))
    for sitemap_url in candidates:
        root = await _fetch_xml(site, sitemap_url)
        if root is not None:
            yield root


def _locs(root: ET.Element, path: str) -> list[str]:
    return [node.text for node in root.findall(path, _SITEMAP_NS) if node.text]


async def _fetch_xml(site: Site, url: str) -> ET.Element | None:
    response = await site.get(url)
    if response is None or response.status_code != 200:
        return None
    try:
        return ET.fromstring(response.text)
    except ET.ParseError:
        return None


def homepage_links(site: Site, homepage: httpx.Response | None) -> list[str]:
    """Unique same-domain links from the homepage, in document order."""
    if homepage is None or homepage.status_code >= 400:
        return []
    tree = HTMLParser(homepage.text)
    base = httpx.URL(site.base_url)
    seen: dict[str, None] = {}
    for anchor in tree.css("a[href]"):
        href = (anchor.attributes.get("href") or "").split("#")[0]
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        url = base.join(href)
        if url.host == site.domain:
            seen[str(url)] = None
    return list(seen)
