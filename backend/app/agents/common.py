"""Decimal-only bounded recommendation helpers, with no financial authority."""
from decimal import Decimal

from .models import recommendation_signature, semantic_fingerprint

ZERO = Decimal("0")
ONE = Decimal("1")


def clamp(value, low=ZERO, high=ONE):
    return max(low, min(high, value))


def mean(values):
    values = list(values)
    return sum(values, ZERO) / Decimal(len(values)) if values else None


def seconds(delta):
    # Avoid a float boundary for microsecond-resolution lifecycle durations.
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(1000000)


def quantile(values, probability):
    """Linear interpolation on sorted Decimal samples, including singleton samples."""
    ordered = sorted(values)
    if not ordered:
        return None
    rank = Decimal(len(ordered) - 1) * probability
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


class VersionedAgent:
    def __init__(self, config):
        self.config = config
        self.version = 0
        self._signature = None

    def _versioned(self, output):
        signature = semantic_fingerprint(recommendation_signature(output))
        if signature != self._signature:
            self.version += 1
            self._signature = signature
        return output.model_copy(update={"version": self.version})

    def recommendation(self, evidence, name, *, score=ZERO, bid_score=None, ask_score=None):
        c = self.config
        spread_strength = getattr(c, name + "_spread_strength")
        size_strength = getattr(c, name + "_size_strength")
        return dict(
            confidence=ONE,
            spread_multiplier=clamp(ONE + spread_strength * score, ONE, c.agent_max_spread_multiplier),
            bid_size_multiplier=clamp(ONE - size_strength * (score if bid_score is None else bid_score), c.agent_min_size_multiplier, ONE),
            ask_size_multiplier=clamp(ONE - size_strength * (score if ask_score is None else ask_score), c.agent_min_size_multiplier, ONE),
            simulated=evidence.simulated, evidence_version=evidence.version, version=self.version,
            updated_at=evidence.updated_at,
        )
