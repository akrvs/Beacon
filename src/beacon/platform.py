"""Detect the commerce/site platform so fixes can say what the owner can
actually change — a Shopify merchant cannot self-host an MCP endpoint."""

from __future__ import annotations

from beacon.fetch import Site

# (platform, header markers, HTML markers) — first match wins
_SIGNATURES: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("Shopify", ("x-shopid", "x-shopify-stage"), ("cdn.shopify.com", ".myshopify.com", "shopify.theme")),
    ("WooCommerce", (), ("woocommerce",)),
    ("Wix", ("x-wix-request-id",), ("static.parastorage.com", "wix.com")),
    ("Squarespace", (), ("squarespace.com", "static1.squarespace")),
    ("BigCommerce", (), ("cdn11.bigcommerce.com", "bigcommerce.com")),
    ("Magento", (), ("/static/version", "mage/requirejs", "magento")),
    ("Webflow", (), ("assets.website-files.com", "data-wf-domain")),
]

# Platforms where the merchant does not control the origin server, so
# "host an endpoint yourself" is not actionable advice.
HOSTED_PLATFORMS = {"Shopify", "Wix", "Squarespace", "BigCommerce", "Webflow"}


async def detect_platform(site: Site) -> str | None:
    response = await site.homepage()
    if response is None or response.status_code >= 400:
        return None
    headers = {key.lower() for key in response.headers}
    html = response.text[:300_000].lower()
    for platform, header_markers, html_markers in _SIGNATURES:
        if any(marker in headers for marker in header_markers):
            return platform
        if any(marker in html for marker in html_markers):
            return platform
    return None
