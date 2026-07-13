"""Check plugin protocol and the Finding model every check emits."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from agentready.fetch import Site


class Layer(str, Enum):
    CRAWL_POLICY = "crawl_policy"
    CONTENT = "content"
    API_MCP = "api_mcp"
    CHECKOUT = "checkout"


class Tier(str, Enum):
    TODAY = "today"  # signals agents actually consume now; drives the headline score
    FUTURE = "future"  # forward-looking readiness (llms.txt, MCP, UCP/ACP/AP2)


class Status(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    INFO = "info"  # informational, excluded from scoring


@dataclass
class Finding:
    id: str
    layer: Layer
    tier: Tier
    status: Status
    weight: int
    summary: str
    fix: str = ""
    evidence: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "layer": self.layer.value,
            "tier": self.tier.value,
            "status": self.status.value,
            "weight": self.weight,
            "summary": self.summary,
            "fix": self.fix,
            "evidence": self.evidence,
        }


@runtime_checkable
class Check(Protocol):
    id: str
    layer: Layer

    async def run(self, site: Site) -> list[Finding]: ...
