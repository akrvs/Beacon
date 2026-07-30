from __future__ import annotations

import json
import re

from selectolax.parser import HTMLParser

from beacon.checks.product import _first_product, _offer_facts, find_product_page
from beacon.fetch import Site

PLACEHOLDER = "FILL_ME"

_CURRENCIES = {"$": "USD", "€": "EUR", "£": "GBP"}
_PRICE_PATTERN = re.compile(r"([$€£])\s?([\d,]+(?:\.\d{1,2})?)")


async def generate_product_schema(site: Site, page_url: str | None = None) -> str | None:
    url = page_url or await find_product_page(site)
    if url is None:
        raise ValueError(
            "No product page detected — pass the product page URL directly, e.g. beacon generate schema https://shop.example/products/widget"
        )
    response = await site.get(url)
    if response is None or response.status_code >= 400:
        raise ValueError(f"Could not fetch {url}")

    tree = HTMLParser(response.text)
    existing = _first_product(tree)
    price, currency, availability = _offer_facts(existing) if existing else ("", "", "")
    if price and currency and availability:
        return None

    name = _meta_property(tree, "og:title") or _text(tree, "title") or _text(tree, "h1")
    description = _meta_name(tree, "description") or _meta_property(tree, "og:description")
    image = _meta_property(tree, "og:image")
    scraped_price, scraped_currency = _scraped_price(tree)
    if existing is not None:
        name = str(existing.get("name") or "") or name
        description = str(existing.get("description") or "") or description

    product: dict = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name or PLACEHOLDER,
        "description": description or PLACEHOLDER,
    }
    if image:
        product["image"] = image
    product["offers"] = {
        "@type": "Offer",
        "url": url,
        "price": price or scraped_price or PLACEHOLDER,
        "priceCurrency": currency or scraped_currency or PLACEHOLDER,
        "availability": availability or "https://schema.org/InStock",
    }
    body = json.dumps(product, indent=2, ensure_ascii=False)
    return f'<script type="application/ld+json">\n{body}\n</script>\n'


def _meta_property(tree: HTMLParser, prop: str) -> str:
    node = tree.css_first(f'meta[property="{prop}"]')
    return (node.attributes.get("content") or "").strip() if node else ""


def _meta_name(tree: HTMLParser, name: str) -> str:
    node = tree.css_first(f'meta[name="{name}"]')
    return (node.attributes.get("content") or "").strip() if node else ""


def _text(tree: HTMLParser, selector: str) -> str:
    node = tree.css_first(selector)
    return node.text(strip=True) if node else ""


def _scraped_price(tree: HTMLParser) -> tuple[str, str]:
    body = tree.body
    if body is None:
        return "", ""
    match = _PRICE_PATTERN.search(body.text(separator=" "))
    if match is None:
        return "", ""
    return match[2].replace(",", ""), _CURRENCIES[match[1]]
