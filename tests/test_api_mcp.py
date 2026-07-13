import json

import httpx
import respx

from beacon.checks.api_mcp import ApiMcpCheck
from beacon.checks.base import Status, Tier
from beacon.checks.checkout import CheckoutCheck
from beacon.fetch import Fetcher, Site

BASE = "https://api.example"


def make_site() -> Site:
    client = httpx.AsyncClient(follow_redirects=True)
    return Site(BASE, fetcher=Fetcher(BASE, client=client))


def respond_404_except(overrides: dict[str, httpx.Response]) -> None:
    for url, response in overrides.items():
        respx.get(url).mock(return_value=response)
    respx.get(url__startswith=BASE).mock(return_value=httpx.Response(404))


@respx.mock
async def test_all_signals_present():
    respond_404_except(
        {
            f"{BASE}/llms.txt": httpx.Response(
                200, text="# Acme\n\n> Widgets", headers={"content-type": "text/plain"}
            ),
            f"{BASE}/openapi.json": httpx.Response(
                200, text=json.dumps({"openapi": "3.1.0", "info": {"title": "Acme API"}})
            ),
            f"{BASE}/.well-known/mcp.json": httpx.Response(
                200, text=json.dumps({"endpoint": "/mcp"})
            ),
        }
    )
    site = make_site()
    findings = {f.id: f for f in await ApiMcpCheck().run(site)}
    await site.aclose()
    assert findings["llms-txt"].status is Status.PASS
    assert findings["openapi-spec"].status is Status.PASS
    assert "Acme API" in findings["openapi-spec"].evidence
    assert findings["mcp-endpoint"].status is Status.PASS
    assert all(f.tier is Tier.FUTURE for f in findings.values())


@respx.mock
async def test_spa_catch_all_html_is_not_counted():
    spa = httpx.Response(200, text="<!doctype html><html>app</html>", headers={"content-type": "text/html"})
    respond_404_except({f"{BASE}/llms.txt": spa, f"{BASE}/.well-known/mcp.json": spa})
    site = make_site()
    findings = {f.id: f for f in await ApiMcpCheck().run(site)}
    await site.aclose()
    assert findings["llms-txt"].status is Status.FAIL
    assert findings["openapi-spec"].status is Status.WARN
    assert findings["mcp-endpoint"].status is Status.FAIL


@respx.mock
async def test_checkout_signals_absent():
    respond_404_except({})
    site = make_site()
    (absent,) = await CheckoutCheck().run(site)
    await site.aclose()
    assert absent.status is Status.FAIL
    assert absent.tier is Tier.FUTURE


@respx.mock
async def test_checkout_signals_present():
    respond_404_except(
        {f"{BASE}/.well-known/ucp.json": httpx.Response(200, text='{"version": 1}')}
    )
    site = make_site()
    (present,) = await CheckoutCheck().run(site)
    await site.aclose()
    assert present.status is Status.PASS
    assert "UCP" in present.summary
