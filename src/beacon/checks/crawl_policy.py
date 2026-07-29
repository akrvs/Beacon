"""Crawl-policy checks: robots.txt rules for AI crawlers, sitemap availability."""

from __future__ import annotations

from datetime import datetime, timezone

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.discover import sitemap_lastmods
from beacon.fetch import Site
from beacon.robots import parse_robots

MAX_SITEMAP_AGE_DAYS = 90

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
            findings.extend(await self._freshness_findings(site))
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
        findings.extend(await self._freshness_findings(site))
        return findings

    async def _freshness_findings(self, site: Site) -> list[Finding]:
        stamps = await sitemap_lastmods(site)
        if stamps is None:
            return []
        dates = []
        for stamp in stamps:
            try:
                parsed = datetime.fromisoformat(stamp.strip())
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            dates.append(parsed)
        if not dates:
            return [
                Finding(
                    id="sitemap-freshness",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.INFO,
                    weight=0,
                    summary="Sitemap has no lastmod dates — agents can't tell how fresh the catalog is",
                )
            ]
        age_days = (datetime.now(timezone.utc) - max(dates)).days
        if age_days <= MAX_SITEMAP_AGE_DAYS:
            return [
                Finding(
                    id="sitemap-freshness",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.PASS,
                    weight=1,
                    summary=f"Sitemap is fresh — newest lastmod is {max(age_days, 0)} day(s) old",
                )
            ]
        return [
            Finding(
                id="sitemap-freshness",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.WARN,
                weight=1,
                summary=f"Newest sitemap lastmod is {age_days} days old — the catalog looks unmaintained to agents",
                fix="Regenerate the sitemap on publish so lastmod reflects reality (most platforms do this automatically)",
            )
        ]

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
