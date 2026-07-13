"""Turn findings into per-layer and headline scores.

The headline score uses only Tier TODAY findings; Tier FUTURE readiness is
scored separately so unproven standards never dominate the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentready.checks.base import Finding, Layer, Status, Tier

_CREDIT = {Status.PASS: 1.0, Status.WARN: 0.5, Status.FAIL: 0.0}


@dataclass
class TierScore:
    earned: float = 0.0
    possible: float = 0.0

    @property
    def percent(self) -> int | None:
        if self.possible == 0:
            return None
        return round(100 * self.earned / self.possible)


@dataclass
class ScoreCard:
    today: TierScore
    future: TierScore
    layers: dict[Layer, dict[Tier, TierScore]]

    def to_dict(self) -> dict:
        return {
            "score_today": self.today.percent,
            "score_future": self.future.percent,
            "layers": {
                layer.value: {tier.value: ts.percent for tier, ts in tiers.items()}
                for layer, tiers in self.layers.items()
            },
        }


def score(findings: list[Finding]) -> ScoreCard:
    totals = {Tier.TODAY: TierScore(), Tier.FUTURE: TierScore()}
    layers: dict[Layer, dict[Tier, TierScore]] = {}
    for finding in findings:
        if finding.status is Status.INFO or finding.weight == 0:
            continue
        credit = _CREDIT[finding.status] * finding.weight
        for bucket in (
            totals[finding.tier],
            layers.setdefault(finding.layer, {}).setdefault(finding.tier, TierScore()),
        ):
            bucket.earned += credit
            bucket.possible += finding.weight
    return ScoreCard(today=totals[Tier.TODAY], future=totals[Tier.FUTURE], layers=layers)
