import json

import httpx
import respx

from beacon.checks.base import Status
from beacon.checks.product import ProductCheck
from beacon.fetch import Fetcher, Site

BASE = "https://shop.example"

SITEMAP = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{BASE}/about</loc></url>
  <url><loc>{BASE}/products/widget</loc></url>
</urlset>"""


def product_page(product: dict | None) -> httpx.Response:
    script = (
        f'<script type="application/ld+json">{json.dumps(product)}</script>' if product else ""
    )
    return httpx.Response(
        200,
        text=f"<html><head><title>Widget</title>{script}</head><body><main>w</main></body></html>",
        headers={"content-type": "text/html"},
    )


def make_site() -> Site:
    client = httpx.AsyncClient(follow_redirects=True)
    return Site(BASE, fetcher=Fetcher(BASE, client=client))


async def run_check(product: dict | None, sitemap: str = SITEMAP):
    respx.get(f"{BASE}/robots.txt").respond(200, text=f"Sitemap: {BASE}/sitemap.xml\n")
    respx.get(f"{BASE}/sitemap.xml").respond(200, text=sitemap)
    respx.get(f"{BASE}/products/widget").mock(return_value=product_page(product))
    respx.get(url__startswith=BASE).respond(404)
    site = make_site()
    (finding,) = await ProductCheck().run(site)
    await site.aclose()
    return finding


@respx.mock
async def test_complete_product_jsonld_passes():
    finding = await run_check(
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Widget",
            "offers": {
                "@type": "Offer",
                "price": "19.99",
                "priceCurrency": "EUR",
                "availability": "https://schema.org/InStock",
            },
        }
    )
    assert finding.status is Status.PASS
    assert "19.99 EUR" in finding.evidence and "InStock" in finding.evidence


@respx.mock
async def test_shopify_product_group_variants_are_found():
    finding = await run_check(
        {
            "@context": "https://schema.org",
            "@type": "ProductGroup",
            "name": "Widget",
            "hasVariant": [
                {
                    "@type": "Product",
                    "name": "Widget — Blue",
                    "offers": {
                        "@type": "Offer",
                        "price": "24.00",
                        "priceCurrency": "USD",
                        "availability": "https://schema.org/InStock",
                    },
                }
            ],
        }
    )
    assert finding.status is Status.PASS
    assert "24.00 USD" in finding.evidence


@respx.mock
async def test_product_without_offer_facts_warns():
    finding = await run_check({"@type": "Product", "name": "Widget"})
    assert finding.status is Status.WARN
    assert "price" in finding.summary


@respx.mock
async def test_commerce_page_without_jsonld_fails():
    respx.get(f"{BASE}/robots.txt").respond(200, text=f"Sitemap: {BASE}/sitemap.xml\n")
    respx.get(f"{BASE}/sitemap.xml").respond(200, text=SITEMAP)
    respx.get(f"{BASE}/products/widget").respond(
        200,
        text="<html><body><main><h1>Widget</h1><p>$19.99</p><button>Add to cart</button></main></body></html>",
        headers={"content-type": "text/html"},
    )
    respx.get(url__startswith=BASE).respond(404)
    site = make_site()
    (finding,) = await ProductCheck().run(site)
    await site.aclose()
    assert finding.status is Status.FAIL


@respx.mock
async def test_marketing_product_page_is_unscored():
    finding = await run_check(None)  # /products/widget page with no commerce signals
    assert finding.status is Status.INFO
    assert finding.weight == 0
    assert "marketing" in finding.summary


@respx.mock
async def test_no_product_page_is_unscored_info():
    finding = await run_check(
        None,
        sitemap=f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{BASE}/about</loc></url>
</urlset>""",
    )
    assert finding.status is Status.INFO
    assert finding.weight == 0
