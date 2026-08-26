"""User-defined checks authored as YAML, no Python required.

Files live in $BEACON_HOME/checks/*.yaml. Each file holds a `checks` list;
every check probes paths and asserts on status/text/headers, then emits one
Finding (PASS, or the configured severity when an assertion misses).

    checks:
      - id: partner-api
        layer: api_mcp
        tier: today
        weight: 2
        on_fail: warn
        probes:
          - path: /api/status
            expect_status: 200
            text_contains: ["ok"]
            header_exists: x-build
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import yaml

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.config import beacon_home
from beacon.fetch import Site

_SEVERITY = {"pass": Status.PASS, "warn": Status.WARN, "fail": Status.FAIL}


@dataclass(frozen=True)
class Probe:
    path: str
    expect_status: int | None = None
    text_contains: tuple[str, ...] = ()
    header_exists: str | None = None


class CustomCheck:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.id = str(spec["id"])
        self.layer = Layer(spec.get("layer", "content"))
        self.tier = Tier(spec.get("tier", "today"))
        self.weight = int(spec.get("weight", 1))
        self.on_fail = _SEVERITY[spec.get("on_fail", "fail")]
        self.probes = [
            Probe(
                path=str(probe["path"]),
                expect_status=(
                    int(probe["expect_status"]) if probe.get("expect_status") else None
                ),
                text_contains=tuple(probe.get("text_contains") or ()),
                header_exists=probe.get("header_exists"),
            )
            for probe in spec.get("probes") or []
        ]
        if not self.probes:
            raise ValueError(f"check {self.id!r} has no probes")

    async def run(self, site: Site) -> list[Finding]:
        verdicts = await asyncio.gather(*(self._probe(site, p) for p in self.probes))
        misses = [evidence for evidence in verdicts if evidence is not None]
        if not misses:
            return [
                Finding(
                    id=self.id,
                    layer=self.layer,
                    tier=self.tier,
                    status=Status.PASS,
                    weight=self.weight,
                    summary=f"Custom check {self.id} passed ({len(self.probes)} probe(s))",
                )
            ]
        return [
            Finding(
                id=self.id,
                layer=self.layer,
                tier=self.tier,
                status=self.on_fail,
                weight=self.weight,
                summary=f"Custom check {self.id} failed {len(misses)} assertion(s)",
                evidence="; ".join(misses[:3]),
            )
        ]

    async def _probe(self, site: Site, probe: Probe) -> str | None:
        """Return evidence text when an assertion fails, None when it holds."""
        response = await site.get(probe.path)
        if response is None:
            return f"{probe.path}: unreachable"
        if probe.expect_status is not None and response.status_code != probe.expect_status:
            return f"{probe.path}: HTTP {response.status_code}, wanted {probe.expect_status}"
        for needle in probe.text_contains:
            if needle.lower() not in response.text.lower():
                return f"{probe.path}: body does not contain {needle!r}"
        if probe.header_exists and probe.header_exists.lower() not in {
            key.lower() for key in response.headers
        }:
            return f"{probe.path}: missing header {probe.header_exists}"
        return None


def load_custom_checks() -> list[CustomCheck]:
    """Every valid check from $BEACON_HOME/checks/*.yaml, stable file order."""
    directory = beacon_home() / "checks"
    if not directory.is_dir():
        return []
    checks: list[CustomCheck] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            specs = doc["checks"] if isinstance(doc, dict) else None
            if not isinstance(specs, list):
                continue
            checks.extend(CustomCheck(spec) for spec in specs)
        except Exception:
            continue  # a broken user file must never take audits down
    return checks
