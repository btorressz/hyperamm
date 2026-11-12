"""Canonical, self-verified *configuration* receipts, not execution attestation."""
from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from app.research_replay.models import Fingerprint
from app.simulation.models import stable_fingerprint
from .models import PortfolioEvidence, PortfolioResearchConfig, CONTRACT_VERSION


class PortfolioResearchProvenance(PortfolioEvidence):
    contract_version: Literal["phase17-portfolio-research-v1"] = CONTRACT_VERSION
    config: PortfolioResearchConfig
    config_fingerprint: Fingerprint
    allocation_fingerprint: Fingerprint
    market_capture_fingerprints: tuple[Fingerprint, ...]
    provenance_fingerprint: Fingerprint
    source_authenticated: Literal[False] = False
    results_engine_attested: Literal[False] = False
    licensing_independently_verified: Literal[False] = False
    synchronized_market_windows_verified: Literal[False] = False
    simulated: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    @staticmethod
    def expected(config: PortfolioResearchConfig) -> dict:
        canonical = config.canonical_payload()
        alloc = stable_fingerprint({
            "budget": canonical["budget"], "allocations": canonical["allocations"]})
        per_market = tuple(s.captured.fingerprint for s in
                           sorted(config.scenarios, key=lambda s: s.market))
        identity = dict(
            contract_version=CONTRACT_VERSION,
            config_fingerprint=config.fingerprint(),
            allocation_fingerprint=alloc,
            market_capture_fingerprints=per_market,
        )
        return {**identity, "provenance_fingerprint": stable_fingerprint(identity)}

    @model_validator(mode="after")
    def verify_receipt(self):
        expected = type(self).expected(self.config)
        if any(getattr(self, key) != value for key, value in expected.items()):
            raise ValueError("portfolio provenance fingerprint or captured identity mismatch")
        return self

    def verify_config(self, config: PortfolioResearchConfig) -> None:
        self = type(self).model_validate(self)
        if self.config_fingerprint != config.fingerprint():
            raise ValueError("portfolio provenance does not bind the supplied configuration")


def capture_portfolio_provenance(config: PortfolioResearchConfig) -> PortfolioResearchProvenance:
    config = PortfolioResearchConfig.model_validate(config)
    return PortfolioResearchProvenance(config=config,
                                       **PortfolioResearchProvenance.expected(config))
