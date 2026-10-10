"""Deterministic Python-owned preset catalog; version definitions when changed."""
from pydantic import BaseModel, ConfigDict
from .research_vault import LIMITATIONS, ResearchVaultConfig


class ResearchPreset(BaseModel):
    model_config = ConfigDict(frozen=True)
    preset_id: str
    name: str
    description: str
    version: str = "1"
    config: ResearchVaultConfig

    def response(self):
        return {**self.model_dump(exclude={"config"}), "config": self.config.canonical(),
                "config_fingerprint": self.config.fingerprint(), "limitations": list(LIMITATIONS)}


PRESETS = (
    ResearchPreset(preset_id="conservative-capital", name="Conservative Capital",
        description="Hypothetical lower full-notional utilization; no claim of lower real-world risk.",
        config=ResearchVaultConfig(initial_equity_quote="50000", max_capital_utilization="0.35",
                                  paper_fee_model_enabled=True)),
    ResearchPreset(preset_id="balanced-research", name="Balanced Research",
        description="General-purpose research capital with explicit hypothetical maker/taker fees.",
        config=ResearchVaultConfig(max_capital_utilization="0.75", paper_fee_model_enabled=True)),
    ResearchPreset(preset_id="high-cost-stress", name="High-Cost Stress",
        description="Stress test of higher hypothetical costs and sampled funding; no execution permissions.",
        config=ResearchVaultConfig(paper_fee_model_enabled=True, paper_maker_fee_bps="10",
                                  paper_taker_fee_bps="25", max_capital_utilization="0.75",
                                  paper_funding_accounting_enabled=True, paper_funding_interval_seconds=60)),
)


def get_preset(preset_id: str) -> ResearchPreset:
    for preset in PRESETS:
        if preset.preset_id == preset_id:
            return preset
    raise ValueError("unknown research preset ID")
