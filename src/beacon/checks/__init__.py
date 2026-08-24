from importlib.metadata import entry_points

from beacon.checks.api_mcp import ApiMcpCheck
from beacon.checks.base import Check, Finding, Layer, Status, Tier
from beacon.checks.checkout import CheckoutCheck
from beacon.checks.content import ContentCheck
from beacon.checks.crawl_policy import CrawlPolicyCheck
from beacon.checks.product import ProductCheck

BUILTIN_CHECKS: list[Check] = [
    CrawlPolicyCheck(),
    ContentCheck(),
    ProductCheck(),
    ApiMcpCheck(),
    CheckoutCheck(),
]

ENTRY_POINT_GROUP = "beacon.checks"


def _plugin_checks() -> list[Check]:
    """Check classes contributed by installed packages through the
    `beacon.checks` entry-point group. A plugin that fails to load or lacks
    the check shape is skipped rather than breaking every audit."""
    plugins: list[Check] = []
    seen = {type(check).id for check in BUILTIN_CHECKS}
    try:
        discovered = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        return []
    for ep in discovered:
        try:
            cls = ep.load()
            instance = cls()
            if (
                getattr(instance, "id", None)
                and isinstance(getattr(instance, "layer", None), Layer)
                and instance.id not in seen
            ):
                seen.add(instance.id)
                plugins.append(instance)
        except Exception:
            continue
    return plugins


ALL_CHECKS: list[Check] = [*BUILTIN_CHECKS, *_plugin_checks()]

__all__ = ["ALL_CHECKS", "BUILTIN_CHECKS", "ENTRY_POINT_GROUP", "Check", "Finding", "Layer", "Status", "Tier"]
