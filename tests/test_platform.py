import httpx
import respx

from beacon.checks.api_mcp import ApiMcpCheck
from beacon.fetch import Fetcher, Site
from beacon.platform import detect_platform

BASE = "https://shop.example"


def make_site() -> Site:
    client = httpx.AsyncClient(follow_redirects=True)
    return Site(BASE, fetcher=Fetcher(BASE, client=client))


@respx.mock
async def test_detects_shopify_from_html():
    respx.get(url__startswith=BASE).respond(
        200,
        text='<html><head><link href="https://cdn.shopify.com/x.css"></head><body>s</body></html>',
        headers={"content-type": "text/html"},
    )
    site = make_site()
    assert await detect_platform(site) == "Shopify"
    await site.aclose()


@respx.mock
async def test_detects_wix_from_header():
    respx.get(url__startswith=BASE).respond(
        200, text="<html><body>w</body></html>", headers={"x-wix-request-id": "abc"}
    )
    site = make_site()
    assert await detect_platform(site) == "Wix"
    await site.aclose()


@respx.mock
async def test_no_platform_detected():
    respx.get(url__startswith=BASE).respond(200, text="<html><body>plain</body></html>")
    site = make_site()
    assert await detect_platform(site) is None
    await site.aclose()


@respx.mock
async def test_hosted_platform_gets_tailored_mcp_fix():
    respx.get(url__startswith=BASE).respond(
        200,
        text='<html><head><script src="https://cdn.shopify.com/a.js"></script></head><body>s</body></html>',
        headers={"content-type": "text/html"},
    )
    site = make_site()
    findings = {f.id: f for f in await ApiMcpCheck().run(site)}
    await site.aclose()
    assert findings["platform-detected"].summary.startswith("Platform detected: Shopify")
    assert "can't self-host" in findings["mcp-endpoint"].fix
    assert "publish llms.txt" in findings["mcp-endpoint"].fix
