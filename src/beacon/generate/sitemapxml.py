"""Draft a sitemap.xml from the homepage's same-domain links."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from beacon.discover import homepage_links
from beacon.fetch import Site


async def generate_sitemap(site: Site) -> str:
    urls = [f"{site.base_url}/"]
    for url in homepage_links(site, await site.homepage()):
        if url.rstrip("/") != site.base_url:
            urls.append(url)
    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for url in urls:
        ET.SubElement(ET.SubElement(urlset, "url"), "loc").text = url
    ET.indent(urlset)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(urlset, encoding="unicode") + "\n"
