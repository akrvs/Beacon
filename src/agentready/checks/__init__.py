from agentready.checks.base import Check, Finding, Layer, Status, Tier
from agentready.checks.crawl_policy import CrawlPolicyCheck

ALL_CHECKS: list[Check] = [
    CrawlPolicyCheck(),
]

__all__ = ["ALL_CHECKS", "Check", "Finding", "Layer", "Status", "Tier"]
