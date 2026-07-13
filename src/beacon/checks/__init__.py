from beacon.checks.api_mcp import ApiMcpCheck
from beacon.checks.base import Check, Finding, Layer, Status, Tier
from beacon.checks.checkout import CheckoutCheck
from beacon.checks.content import ContentCheck
from beacon.checks.crawl_policy import CrawlPolicyCheck

ALL_CHECKS: list[Check] = [
    CrawlPolicyCheck(),
    ContentCheck(),
    ApiMcpCheck(),
    CheckoutCheck(),
]

__all__ = ["ALL_CHECKS", "Check", "Finding", "Layer", "Status", "Tier"]
