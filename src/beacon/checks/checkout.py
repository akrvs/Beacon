"""Agent-checkout readiness (Tier: future) — UCP/ACP/AP2 support signals.

These protocols are still emerging; the check probes the discovery endpoints
each one has proposed and reports honestly that absence is the norm today.
"""

from __future__ import annotations

import asyncio

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.fetch import Site

PROTOCOL_PROBES = {
    "UCP": "/.well-known/ucp.json",
    "ACP": "/.well-known/acp.json",
    "AP2": "/.well-known/ap2.json",
    "x402": "/.well-known/x402",
}


class CheckoutCheck:
    id = "checkout"
    layer = Layer.CHECKOUT

    async def run(self, site: Site) -> list[Finding]:
        responses = await asyncio.gather(
            *(site.get(path) for path in PROTOCOL_PROBES.values())
        )
        supported: list[str] = []
        for name, response in zip(PROTOCOL_PROBES, responses):
            if response is not None and response.status_code == 200:
                body = response.text.lstrip()[:100].lower()
                if not body.startswith(("<!doctype", "<html")):
                    supported.append(name)
        if supported:
            return [
                Finding(
                    id="agentic-commerce-protocols",
                    layer=self.layer,
                    tier=Tier.FUTURE,
                    status=Status.PASS,
                    weight=2,
                    summary=f"Agentic-commerce protocol endpoint(s) detected: {', '.join(supported)}",
                    evidence=", ".join(PROTOCOL_PROBES[name] for name in supported),
                )
            ]
        return [
            Finding(
                id="agentic-commerce-protocols",
                layer=self.layer,
                tier=Tier.FUTURE,
                status=Status.FAIL,
                weight=2,
                summary="No agentic-commerce protocol signals (UCP/ACP/AP2/x402) — normal today, but this is where agent checkout is heading",
                fix="Watch UCP/ACP adoption for your platform; when your commerce stack ships support, advertise the discovery endpoint",
            )
        ]
