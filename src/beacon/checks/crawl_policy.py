"""Crawl-policy checks: robots.txt rules for AI crawlers, sitemap availability."""

from __future__ import annotations

from dataclasses import dataclass, field

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.fetch import Site

# Bots that fetch pages live on behalf of a user or agent session. Blocking
# these makes the site invisible to agents at the moment of use.
AGENT_FETCHERS = [
    "ChatGPT-User",
    "OAI-SearchBot",
    "Claude-User",
    "Claude-SearchBot",
    "PerplexityBot",
    "Perplexity-User",
    "GoogleOther",
    "Amazonbot",
]

# Bots that collect training data. Blocking these is a legitimate business
# choice and should not tank an agent-visibility score.
TRAINING_CRAWLERS = [
    "GPTBot",
    "ClaudeBot",
    "anthropic-ai",
    "CCBot",
    "Google-Extended",
    "Applebot-Extended",
    "meta-externalagent",
    "Bytespider",
]


@dataclass
class RobotsGroup:
    agents: list[str] = field(default_factory=list)
    disallow: list[str] = field(default_factory=list)
    allow: list[str] = field(default_factory=list)


@dataclass
class RobotsFile:
    groups: list[RobotsGroup] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)

    def group_for(self, agent: str) -> RobotsGroup | None:
        """Most specific applicable group per RFC 9309: exact token beats *."""
        agent = agent.lower()
        wildcard = None
        for group in self.groups:
            for token in group.agents:
                if token == agent:
                    return group
                if token == "*" and wildcard is None:
                    wildcard = group
        return wildcard

    def blocks_entirely(self, agent: str) -> bool:
        group = self.group_for(agent)
        if group is None:
            return False
        return "/" in group.disallow and "/" not in group.allow


def parse_robots(text: str) -> RobotsFile:
    robots = RobotsFile()
    current: RobotsGroup | None = None
    agents_open = False  # consecutive user-agent lines share one group
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "sitemap":
            robots.sitemaps.append(value)
        elif key == "user-agent":
            if not agents_open:
                current = RobotsGroup()
                robots.groups.append(current)
                agents_open = True
            current.agents.append(value.lower())
        elif key in ("disallow", "allow") and current is not None:
            agents_open = False
            getattr(current, key).append(value)
        else:
            agents_open = False
    return robots


class CrawlPolicyCheck:
    id = "crawl_policy"
    layer = Layer.CRAWL_POLICY

    async def run(self, site: Site) -> list[Finding]:
        robots_text = await site.robots_txt()
        findings: list[Finding] = []

        if robots_text is None:
            findings.append(
                Finding(
                    id="robots-txt-present",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.WARN,
                    weight=1,
                    summary="No robots.txt found (agents default to allow, but you publish no crawl policy or sitemap pointer)",
                    fix=f"Add a robots.txt at {site.base_url}/robots.txt that allows AI user agents and declares your sitemap",
                )
            )
            findings.append(await self._sitemap_finding(site, declared=[]))
            return findings

        robots = parse_robots(robots_text)
        findings.append(
            Finding(
                id="robots-txt-present",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.PASS,
                weight=1,
                summary="robots.txt is present and parseable",
            )
        )

        blocked_fetchers = [a for a in AGENT_FETCHERS if robots.blocks_entirely(a)]
        if blocked_fetchers:
            findings.append(
                Finding(
                    id="agent-fetchers-allowed",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.FAIL,
                    weight=3,
                    summary=f"robots.txt fully blocks {len(blocked_fetchers)} live agent fetcher(s) — the site is invisible to those agents",
                    fix="Unblock on-demand agent user-agents in robots.txt; keep training-bot rules separate if you want to restrict training",
                    evidence=", ".join(blocked_fetchers),
                )
            )
        else:
            findings.append(
                Finding(
                    id="agent-fetchers-allowed",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.PASS,
                    weight=3,
                    summary="No live agent fetchers (ChatGPT-User, Claude-User, PerplexityBot, ...) are blocked",
                )
            )

        blocked_training = [a for a in TRAINING_CRAWLERS if robots.blocks_entirely(a)]
        if blocked_training:
            findings.append(
                Finding(
                    id="training-crawlers-blocked",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.INFO,
                    weight=0,
                    summary=f"{len(blocked_training)} training crawler(s) are blocked — a legitimate choice, noted for completeness",
                    evidence=", ".join(blocked_training),
                )
            )

        findings.append(await self._sitemap_finding(site, declared=robots.sitemaps))
        return findings

    async def _sitemap_finding(self, site: Site, declared: list[str]) -> Finding:
        if declared:
            return Finding(
                id="sitemap-available",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.PASS,
                weight=2,
                summary="Sitemap declared in robots.txt",
                evidence=declared[0],
            )
        response = await site.get("/sitemap.xml")
        if response is not None and response.status_code == 200:
            return Finding(
                id="sitemap-available",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.WARN,
                weight=2,
                summary="sitemap.xml exists but is not declared in robots.txt",
                fix=f"Add `Sitemap: {site.base_url}/sitemap.xml` to robots.txt",
            )
        return Finding(
            id="sitemap-available",
            layer=self.layer,
            tier=Tier.TODAY,
            status=Status.FAIL,
            weight=2,
            summary="No sitemap found — agents and crawlers cannot discover your catalog systematically",
            fix="Publish a sitemap.xml covering your key pages/products and declare it in robots.txt",
        )
