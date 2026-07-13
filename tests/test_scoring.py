from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.scoring import score


def finding(status, weight=1, tier=Tier.TODAY, layer=Layer.CRAWL_POLICY):
    return Finding(
        id="x", layer=layer, tier=tier, status=status, weight=weight, summary="s"
    )


def test_pass_warn_fail_credit():
    card = score(
        [finding(Status.PASS, 3), finding(Status.WARN, 2), finding(Status.FAIL, 1)]
    )
    assert card.today.percent == round(100 * (3 + 1) / 6) == 67


def test_info_and_zero_weight_excluded():
    card = score([finding(Status.INFO, 5), finding(Status.PASS, 0)])
    assert card.today.percent is None


def test_tiers_scored_independently():
    card = score(
        [
            finding(Status.PASS, 2, tier=Tier.TODAY),
            finding(Status.FAIL, 2, tier=Tier.FUTURE, layer=Layer.API_MCP),
        ]
    )
    assert card.today.percent == 100
    assert card.future.percent == 0
    assert card.layers[Layer.API_MCP][Tier.FUTURE].percent == 0
