"""API/MCP availability checks (Tier: future) — llms.txt, OpenAPI, MCP discovery.

These standards have little confirmed agent consumption today, so every
finding here is Tier.FUTURE and never affects the headline visibility score.
"""

from __future__ import annotations

import asyncio
import json

import httpx

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.discover import sitemap_index_children
from beacon.fetch import Site
from beacon.platform import HOSTED_PLATFORMS, detect_platform

OPENAPI_PROBES = ["/openapi.json", "/swagger.json", "/api/openapi.json", "/.well-known/openapi.json"]
MCP_PROBES = ["/.well-known/mcp.json", "/mcp"]


def _is_real_text(response: httpx.Response | None) -> bool:
    """A 200 that is actually plain text, not an SPA catch-all serving HTML."""
    if response is None or response.status_code != 200:
        return False
    content_type = response.headers.get("content-type", "")
    body = response.text.lstrip()[:100].lower()
    return "html" not in content_type and not body.startswith(("<!doctype", "<html"))


def _openapi_spec(response: httpx.Response | None) -> dict | None:
    if response is None or response.status_code != 200:
        return None
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and ("openapi" in data or "swagger" in data):
        return data
    return None


class ApiMcpCheck:
    id = "api_mcp"
    layer = Layer.API_MCP

    async def run(self, site: Site) -> list[Finding]:
        platform = await detect_platform(site)
        findings = list(
            await asyncio.gather(
                self._llms_txt(site),
                self._openapi(site),
                self._mcp(site, platform),
                self._agentic_sitemap(site),
            )
        )
        if platform is not None:
            findings.insert(
                0,
                Finding(
                    id="platform-detected",
                    layer=self.layer,
                    tier=Tier.FUTURE,
                    status=Status.INFO,
                    weight=0,
                    summary=f"Platform detected: {platform} — fixes below account for what {platform} merchants can actually change",
                ),
            )
        return findings

    async def _llms_txt(self, site: Site) -> Finding:
        response = await site.get("/llms.txt")
        if _is_real_text(response):
            return Finding(
                id="llms-txt",
                layer=self.layer,
                tier=Tier.FUTURE,
                status=Status.PASS,
                weight=2,
                summary="llms.txt is published — a curated map of the site for LLM consumption",
                evidence=site.fetcher.url_for("/llms.txt"),
            )
        return Finding(
            id="llms-txt",
            layer=self.layer,
            tier=Tier.FUTURE,
            status=Status.FAIL,
            weight=2,
            summary="No llms.txt — agents that look for a curated site map won't find one",
            fix="Generate one with `beacon generate llms-txt <domain>` and serve it at /llms.txt",
        )

    async def _openapi(self, site: Site) -> Finding:
        responses = await asyncio.gather(*(site.get(path) for path in OPENAPI_PROBES))
        for path, response in zip(OPENAPI_PROBES, responses):
            spec = _openapi_spec(response)
            if spec:
                title = spec.get("info", {}).get("title", "")
                return Finding(
                    id="openapi-spec",
                    layer=self.layer,
                    tier=Tier.FUTURE,
                    status=Status.PASS,
                    weight=2,
                    summary="A machine-readable OpenAPI spec is discoverable — the raw material for agent integrations",
                    evidence=f"{site.fetcher.url_for(path)}" + (f" ({title})" if title else ""),
                )
        return Finding(
            id="openapi-spec",
            layer=self.layer,
            tier=Tier.FUTURE,
            status=Status.WARN,
            weight=2,
            summary="No OpenAPI spec found at common paths — if an API exists, agents can't discover its shape",
            fix="Publish your API spec at /openapi.json; it is also the input for MCP server generation",
        )

    async def _mcp(self, site: Site, platform: str | None = None) -> Finding:
        responses = await asyncio.gather(*(site.get(path) for path in MCP_PROBES))
        for path, response in zip(MCP_PROBES, responses):
            if _is_real_text(response):
                return Finding(
                    id="mcp-endpoint",
                    layer=self.layer,
                    tier=Tier.FUTURE,
                    status=Status.PASS,
                    weight=3,
                    summary="An MCP discovery endpoint responds — agents can connect via tools instead of scraping",
                    evidence=site.fetcher.url_for(path),
                )
        if platform in HOSTED_PLATFORMS:
            fix = (
                f"{platform} controls your storefront's origin, so you can't self-host an MCP endpoint — "
                f"publish llms.txt instead and adopt {platform}'s native agent/MCP support when it ships"
            )
        else:
            fix = "Scaffold one from your OpenAPI spec with `beacon generate mcp <spec>` and advertise it at /.well-known/mcp.json"
        return Finding(
            id="mcp-endpoint",
            layer=self.layer,
            tier=Tier.FUTURE,
            status=Status.FAIL,
            weight=3,
            summary="No MCP endpoint detected (/.well-known/mcp.json, /mcp)",
            fix=fix,
        )

    async def _agentic_sitemap(self, site: Site) -> Finding:
        children = await sitemap_index_children(site)
        agentic = [url for url in children if "agentic" in url.lower()]
        if agentic:
            return Finding(
                id="agentic-discovery-sitemap",
                layer=self.layer,
                tier=Tier.FUTURE,
                status=Status.PASS,
                weight=1,
                summary="An agentic-discovery sitemap is published — the platform is curating pages for agents",
                evidence=agentic[0],
            )
        return Finding(
            id="agentic-discovery-sitemap",
            layer=self.layer,
            tier=Tier.FUTURE,
            status=Status.INFO,
            weight=0,
            summary="No agentic-discovery sitemap (e.g. Shopify's sitemap_agentic_discovery.xml) — an emerging signal, absence is normal",
        )
