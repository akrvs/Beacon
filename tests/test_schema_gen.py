import json

import pytest
import respx

from beacon.fetch import Site
from beacon.generate.schema import PLACEHOLDER, generate_product_schema

BASE = "https://shop.example"
PAGE = f"{BASE}/products/widget"


async def generate(page_html: str, page_url: str | None = PAGE) -> str | None:
    respx.get(PAGE).respond(200, text=page_html)
    site = Site("shop.example")
    try:
        return await generate_product_schema(site, page_url)
    finally:
        await site.aclose()


def parse_block(block: str) -> dict:
    assert block.startswith('<script type="application/ld+json">')
    assert block.rstrip().endswith("</script>")
    return json.loads(block.split(">", 1)[1].rsplit("<", 1)[0])


@respx.mock
@pytest.mark.asyncio
async def test_draft_from_scraped_page():
    html = (
        "<html><head><title>Widget — Shop</title>"
        '<meta property="og:title" content="Widget">'
        '<meta name="description" content="A fine widget.">'
        '<meta property="og:image" content="https://shop.example/w.jpg">'
        "</head><body><h1>Widget</h1><p>Only $1,299.99 — add to cart</p></body></html>"
    )
    block = await generate(html)
    product = parse_block(block)
    assert product["@type"] == "Product"
    assert product["name"] == "Widget"
    assert product["description"] == "A fine widget."
    assert product["image"] == "https://shop.example/w.jpg"
    assert product["offers"]["price"] == "1299.99"
    assert product["offers"]["priceCurrency"] == "USD"
    assert product["offers"]["availability"] == "https://schema.org/InStock"
    assert product["offers"]["url"] == PAGE


@respx.mock
@pytest.mark.asyncio
async def test_partial_jsonld_is_seeded_and_completed():
    existing = {"@type": "Product", "name": "Widget Pro", "offers": {"price": "49"}}
    html = (
        f'<html><head><script type="application/ld+json">{json.dumps(existing)}</script>'
        "</head><body><p>Buy now for €49</p></body></html>"
    )
    product = parse_block(await generate(html))
    assert product["name"] == "Widget Pro"
    assert product["offers"]["price"] == "49"
    assert product["offers"]["priceCurrency"] == "EUR"
    assert product["description"] == PLACEHOLDER


@respx.mock
@pytest.mark.asyncio
async def test_complete_jsonld_generates_nothing():
    existing = {
        "@type": "Product",
        "name": "Widget",
        "offers": {
            "price": "9.99",
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock",
        },
    }
    html = f'<script type="application/ld+json">{json.dumps(existing)}</script>'
    assert await generate(html) is None


@respx.mock
@pytest.mark.asyncio
async def test_bare_page_gets_placeholders():
    product = parse_block(await generate("<html><body>hello</body></html>"))
    assert product["name"] == PLACEHOLDER
    assert product["offers"]["price"] == PLACEHOLDER
    assert product["offers"]["priceCurrency"] == PLACEHOLDER


@respx.mock
@pytest.mark.asyncio
async def test_no_product_page_raises():
    respx.get(f"{BASE}/robots.txt").respond(404)
    respx.get(url__startswith=BASE).respond(404)
    site = Site("shop.example")
    try:
        with pytest.raises(ValueError):
            await generate_product_schema(site)
    finally:
        await site.aclose()
