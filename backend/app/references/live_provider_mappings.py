"""Explicit observational mapping registry; never inherits operational ETH config."""
from typing import Literal
from pydantic import AwareDatetime, model_validator
from app.market_data.live_models import Evidence, LiveMarketId
from app.references.models import ProviderId, ReferenceTransport, SourceType

NATIVE = (ProviderId.HYPERLIQUID_MID, ProviderId.HYPERLIQUID_ORACLE, ProviderId.HYPERLIQUID_MARK)
EXTERNAL = (ProviderId.REDSTONE, ProviderId.KRAKEN, ProviderId.COINGECKO, ProviderId.YAHOO_FINANCE)
ROLES = {ProviderId.HYPERLIQUID_MID: SourceType.EXECUTION_VENUE,
    ProviderId.HYPERLIQUID_ORACLE: SourceType.NATIVE_ORACLE, ProviderId.HYPERLIQUID_MARK: SourceType.PERP_MARK,
    ProviderId.REDSTONE: SourceType.ORACLE, ProviderId.KRAKEN: SourceType.VENUE_REFERENCE,
    ProviderId.COINGECKO: SourceType.AGGREGATOR_REFERENCE, ProviderId.YAHOO_FINANCE: SourceType.AGGREGATOR_REFERENCE}
# Validation allowlists are not default configuration or evidence of live support.
SYMBOLS = {
    ProviderId.REDSTONE: {'BTC': 'BTC', 'ETH': 'ETH', 'SOL': 'SOL'},
    ProviderId.KRAKEN: {'BTC': 'BTC/USD', 'ETH': 'ETH/USD', 'SOL': 'SOL/USD'},
    ProviderId.COINGECKO: {'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana'},
    ProviderId.YAHOO_FINANCE: {'BTC': 'BTC-USD', 'ETH': 'ETH-USD'},
}


class LiveProviderMapping(Evidence):
    market: LiveMarketId
    provider: ProviderId
    native_symbol: str | None = None
    expected_source_id: str | None = None
    transport: ReferenceTransport
    mapping_status: Literal['VALIDATED', 'UNCONFIGURED', 'UNVERIFIED', 'UNAVAILABLE']
    enabled: bool = False
    last_validated_configuration: AwareDatetime | None = None
    authority: Literal['NONE'] = 'NONE'

    @model_validator(mode='after')
    def mapping_identity(self):
        if self.provider in EXTERNAL:
            expected = SYMBOLS[self.provider].get(self.market)
            if self.native_symbol is not None and (expected is None or self.native_symbol != expected):
                raise ValueError('wrong or unsupported provider asset mapping')
            if self.mapping_status == 'VALIDATED':
                expected_id = (f'redstone-primary-prod:{expected}' if self.transport == ReferenceTransport.LIVE_WS else
                    f'redstone-public-http:{expected}') if self.provider == ProviderId.REDSTONE else expected
                transports = {ProviderId.REDSTONE: {'LIVE_WS', 'PUBLIC_HTTP'}, ProviderId.KRAKEN: {'LIVE_WS'},
                    ProviderId.COINGECKO: {'REST'}, ProviderId.YAHOO_FINANCE: {'LIVE_WS'}}
                if (expected is None or self.native_symbol != expected or self.expected_source_id != expected_id or
                    self.transport not in transports[self.provider] or self.last_validated_configuration is None):
                    raise ValueError('mapping lacks validated provider configuration')
            # This phase deliberately ships contracts, not new external collectors.
            if self.enabled:
                raise ValueError('optional external stream collectors are not enabled in phase152')
        elif self.mapping_status == 'VALIDATED':
            expected = f'hyperliquid:{self.market}:{self.provider.value}'
            if (self.native_symbol != self.market or self.expected_source_id != expected or
                self.transport != 'NATIVE' or self.last_validated_configuration is None):
                raise ValueError('native mapping identity mismatch')
        if self.enabled and self.mapping_status != 'VALIDATED':
            raise ValueError('enabled mapping must be validated')
        return self


def external_mappings(market):
    return tuple(LiveProviderMapping(market=market, provider=p,
        transport='REST' if p == ProviderId.COINGECKO else 'LIVE_WS',
        mapping_status='UNAVAILABLE' if p == ProviderId.YAHOO_FINANCE and market == 'SOL' else 'UNCONFIGURED')
        for p in EXTERNAL)


def validate_provider_evidence(mapping, evidence):
    """Pure identity gate reusable by future observational transports; no mutation."""
    if (mapping.mapping_status != 'VALIDATED' or evidence.market != mapping.market or
        evidence.provider != mapping.provider or evidence.source_type != ROLES[mapping.provider] or
        evidence.source_id != mapping.expected_source_id or evidence.transport != mapping.transport or
        evidence.simulated):
        raise ValueError('provider evidence does not match validated mapping')
    return evidence
