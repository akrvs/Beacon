import httpx
import respx

from beacon.fetch import Fetcher, Site
from beacon.generate.llmstxt import generate_llms_full_txt, generate_llms_txt

BASE = "https://shop.example"

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://shop.example/products/widget</loc></url>
  <url><loc>https://shop.example/docs/shipping</loc></url>
</urlset>"""


def page(title: str, description: str = "") -> httpx.Response:
    meta = f'<meta name="description" content="{description}">' if description else ""
    return httpx.Response(
        200,
        text=f"<html><head><title>{title}</title>{meta}</head><body><main>x</main></body></html>",
        headers={"content-type": "text/html"},
    )


def make_site() -> Site:
    client = httpx.AsyncClient(follow_redirects=True)
    return Site(BASE, fetcher=Fetcher(BASE, client=client))


@respx.mock
async def test_generates_from_sitemap():
    respx.get(f"{BASE}/robots.txt").respond(200, text=f"Sitemap: {BASE}/sitemap.xml\n")
    respx.get(f"{BASE}/sitemap.xml").respond(200, text=SITEMAP)
    respx.get(f"{BASE}/products/widget").mock(return_value=page("Widget", "Our best widget"))
    respx.get(f"{BASE}/docs/shipping").mock(return_value=page("Shipping"))
    # respx treats a path-less URL pattern as host-wide; register it last so it
    # only catches the homepage request
    respx.get(BASE).mock(return_value=page("Acme Shop", "Widgets worldwide"))

    site = make_site()
    text = await generate_llms_txt(site)
    await site.aclose()

    assert text.startswith("# Acme Shop\n\n> Widgets worldwide\n")
    assert "## Products" in text and "## Docs" in text
    assert "- [Widget](https://shop.example/products/widget): Our best widget" in text
    assert "- [Shipping](https://shop.example/docs/shipping)\n" in text


@respx.mock
async def test_generates_llms_full_with_page_text():
    respx.get(f"{BASE}/robots.txt").respond(200, text=f"Sitemap: {BASE}/sitemap.xml\n")
    respx.get(f"{BASE}/sitemap.xml").respond(200, text=SITEMAP)
    respx.get(f"{BASE}/products/widget").respond(
        200,
        text=(
            "<html><head><title>Widget</title></head>"
            "<body><script>ignored()</script><main>A fine widget for 9.99</main></body></html>"
        ),
        headers={"content-type": "text/html"},
    )
    respx.get(f"{BASE}/docs/shipping").respond(404)
    respx.get(BASE).mock(return_value=page("Acme Shop", "Widgets worldwide"))

    site = make_site()
    text = await generate_llms_full_txt(site)
    await site.aclose()

    assert text.startswith("# Acme Shop\n\n> Widgets worldwide\n")
    assert "## Widget\nhttps://shop.example/products/widget\n\nA fine widget for 9.99" in text
    assert "ignored()" not in text
    assert "shipping" not in text
    assert not text.rstrip().endswith("---")


@respx.mock
async def test_falls_back_to_homepage_links():
    homepage = httpx.Response(
        200,
        text=(
            "<html><head><title>Acme</title></head><body>"
            f'<a href="/about">About</a> <a href="{BASE}/pricing">Pricing</a> '
            '<a href="https://elsewhere.example/x">External</a> <a href="mailto:a@b.c">Mail</a>'
            "</body></html>"
        ),
        headers={"content-type": "text/html"},
    )
    respx.get(f"{BASE}/robots.txt").respond(404)
    respx.get(f"{BASE}/sitemap.xml").respond(404)
    respx.get(f"{BASE}/about").mock(return_value=page("About Acme"))
    respx.get(f"{BASE}/pricing").mock(return_value=page("Pricing"))
    respx.get(BASE).mock(return_value=homepage)

    site = make_site()
    text = await generate_llms_txt(site)
    await site.aclose()

    assert "- [About Acme](https://shop.example/about)" in text
    assert "- [Pricing](https://shop.example/pricing)" in text
    assert "elsewhere.example" not in text
