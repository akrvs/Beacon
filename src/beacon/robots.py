"""robots.txt parsing and RFC 9309 rule matching."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


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

    def allows(self, agent: str, path: str) -> bool:
        """RFC 9309 path matching: longest matching rule wins, allow on ties."""
        group = self.group_for(agent)
        if group is None:
            return True
        best_length = -1
        best_allow = True
        for rules, verdict in ((group.allow, True), (group.disallow, False)):
            for rule in rules:
                if not rule or not _rule_matches(rule, path):
                    continue
                if len(rule) > best_length or (len(rule) == best_length and verdict):
                    best_length = len(rule)
                    best_allow = verdict
        return best_allow


def _rule_matches(rule: str, path: str) -> bool:
    anchored = rule.endswith("$")
    if anchored:
        rule = rule[:-1]
    pattern = ".*".join(re.escape(part) for part in rule.split("*"))
    return re.fullmatch(pattern if anchored else f"{pattern}.*", path) is not None


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
