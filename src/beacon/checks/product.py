"""Product-page deep audit: does a real product page carry the Product/Offer
JSON-LD (price, availability) that shopping surfaces and agents consume?

Sites with no detectable product page (SaaS, content sites) get a zero-weight
INFO finding — absence of a catalog must never hurt their score.
"""

from __future__ import annotations

import json
import re

import httpx
from selectolax.parser import HTMLParser

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.discover import crawlable_urls
from beacon.fetch import Site

PRODUCT_PATH_HINTS = ("/product/", "/products/", "/item/", "/p/", "/shop/")


class ProductCheck:
    id = "product"
    layer = Layer.CONTENT

    async def run(self, site: Site) -> list[Finding]:
        product_url = await find_product_page(site)
        if product_url is None:
            return [
                Finding(
                    id="product-markup",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.INFO,
                    weight=0,
                    summary="No product page detected — product markup not evaluated (fine for non-commerce sites)",
                )
            ]

        response = await site.get(product_url)
        if response is None or response.status_code >= 400:
            return [
                Finding(
                    id="product-markup",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.FAIL,
                    weight=3,
                    summary=f"Product page could not be fetched ({product_url})",
                    fix="Ensure product pages return HTTP 200 to non-browser user agents",
                )
            ]

        tree = HTMLParser(response.text)
        product = _first_product(tree)
        if product is None:
            if not _looks_like_commerce(tree):
                return [
                    Finding(
                        id="product-markup",
                        layer=self.layer,
                        tier=Tier.TODAY,
                        status=Status.INFO,
                        weight=0,
                        summary="A /product/ page was found but shows no commerce signals (cart, buy, prices) — treated as marketing, not scored",
                        evidence=product_url,
                    )
                ]
            return [
                Finding(
                    id="product-markup",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.FAIL,
                    weight=3,
                    summary="Product page has no Product JSON-LD — shopping agents can't read what you sell",
                    fix="Add schema.org Product JSON-LD with offers (price, priceCurrency, availability) to every product page",
                    evidence=product_url,
                )
            ]

        price, currency, availability = _offer_facts(product)
        missing = [
            label
            for label, value in [
                ("price", price),
                ("priceCurrency", currency),
                ("availability", availability),
            ]
            if not value
        ]
        if not missing:
            return [
                Finding(
                    id="product-markup",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.PASS,
                    weight=3,
                    summary="Product JSON-LD is complete — price, currency, and availability are machine-readable",
                    evidence=f"{product_url} ({price} {currency}, {availability.rsplit('/', 1)[-1]})",
                )
            ]
        return [
            Finding(
                id="product-markup",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.WARN,
                weight=3,
                summary=f"Product JSON-LD found but offers are missing {', '.join(missing)} — agents must scrape those from prose",
                fix="Complete the offers object: price, priceCurrency, and availability",
                evidence=product_url,
            )
        ]


async def find_product_page(site: Site) -> str | None:
    for url in await crawlable_urls(site):
        path = httpx.URL(url).path.lower()
        if any(hint in path for hint in PRODUCT_PATH_HINTS) and path.rstrip("/").count("/") >= 2:
            return url
    return None


_COMMERCE_PATTERN = re.compile(
    r"add to (?:cart|bag|basket)|buy now|checkout|[$€£]\s?\d", re.IGNORECASE
)


def _looks_like_commerce(tree: HTMLParser) -> bool:
    body = tree.body
    return body is not None and bool(_COMMERCE_PATTERN.search(body.text(separator=" ")))


def _first_product(tree: HTMLParser) -> dict | None:
    """First Product entity with priced offers, else any Product. Searches
    nested structures too — Shopify wraps variants in ProductGroup.hasVariant."""
    products: list[dict] = []
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.text())
        except (json.JSONDecodeError, TypeError):
            continue
        products.extend(_find_products(data))
    for product in products:
        if _offer_facts(product)[0]:
            return product
    return products[0] if products else None


def _find_products(obj: object) -> list[dict]:
    found: list[dict] = []
    if isinstance(obj, dict):
        declared = obj.get("@type")
        types = declared if isinstance(declared, list) else [declared]
        if "Product" in types:
            found.append(obj)
        for value in obj.values():
            found.extend(_find_products(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_products(item))
    return found


def _offer_facts(product: dict) -> tuple[str, str, str]:
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers and isinstance(offers[0], dict) else {}
    if not isinstance(offers, dict):
        offers = {}
    price = str(offers.get("price") or offers.get("lowPrice") or "")
    currency = str(offers.get("priceCurrency") or "")
    availability = str(offers.get("availability") or "")
    return price, currency, availability
