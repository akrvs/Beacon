"""API/MCP availability checks (Tier: future) — llms.txt, OpenAPI, MCP discovery.

These standards have little confirmed agent consumption today, so every
finding here is Tier.FUTURE and never affects the headline visibility score.
"""

from __future__ import annotations

import json

import httpx

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.fetch import Site

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
        return [
            await self._llms_txt(site),
            await self._openapi(site),
            await self._mcp(site),
        ]

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
        for path in OPENAPI_PROBES:
            spec = _openapi_spec(await site.get(path))
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

    async def _mcp(self, site: Site) -> Finding:
        for path in MCP_PROBES:
            if _is_real_text(await site.get(path)):
                return Finding(
                    id="mcp-endpoint",
                    layer=self.layer,
                    tier=Tier.FUTURE,
                    status=Status.PASS,
                    weight=3,
                    summary="An MCP discovery endpoint responds — agents can connect via tools instead of scraping",
                    evidence=site.fetcher.url_for(path),
                )
        return Finding(
            id="mcp-endpoint",
            layer=self.layer,
            tier=Tier.FUTURE,
            status=Status.FAIL,
            weight=3,
            summary="No MCP endpoint detected (/.well-known/mcp.json, /mcp)",
            fix="Scaffold one from your OpenAPI spec with `beacon generate mcp <spec>` and advertise it at /.well-known/mcp.json",
        )
