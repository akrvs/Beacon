from beacon.checks.api_mcp import ApiMcpCheck
from beacon.checks.base import Check, Finding, Layer, Status, Tier
from beacon.checks.checkout import CheckoutCheck
from beacon.checks.content import ContentCheck
from beacon.checks.crawl_policy import CrawlPolicyCheck
from beacon.checks.product import ProductCheck

ALL_CHECKS: list[Check] = [
    CrawlPolicyCheck(),
    ContentCheck(),
    ProductCheck(),
    ApiMcpCheck(),
    CheckoutCheck(),
]

__all__ = ["ALL_CHECKS", "Check", "Finding", "Layer", "Status", "Tier"]
