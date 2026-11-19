"""Normalize public Hyperliquid financial observations within a discovery generation."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.accounting.config import bounded_exact_decimal
from app.market_data.live_models import Evidence
from app.market_data.market_universe_contracts import (
    MarketUniverseMetadata, Network, UtcDatetime, _strict_bool, evaluate_discovery,
)
from app.risk.market_risk_contracts import RiskFinancialUnit
from app.simulation.models import stable_fingerprint

TokenIndex = Annotated[StrictInt, Field(ge=0, le=2**31 - 1)]
Leverage = Annotated[StrictInt, Field(ge=1, le=100)]
TableId = Annotated[StrictInt, Field(ge=1, le=2**31 - 1)]
MAINNET_USDC_ID = "0x6d1e7cde53ba9467b783cb7c530ce054"
LowerBound = Annotated[Decimal, BeforeValidator(bounded_exact_decimal), Field(ge=0)]
MarketMode = Literal["STRICT_ISOLATED", "NO_CROSS", "CROSS_ELIGIBLE", "ISOLATED_UNSPECIFIED", "UNKNOWN"]
SourceStatus = Literal["SOURCE_OBSERVED", "STALE", "UNAVAILABLE", "UNSUPPORTED"]
CollateralIssue = Literal["COLLATERAL_MISSING", "COLLATERAL_INVALID", "TOKEN_METADATA_UNAVAILABLE", "TOKEN_UNRESOLVED"]
ModeIssue = Literal["MARGIN_MODE_MISSING", "MARGIN_MODE_UNSUPPORTED", "MARGIN_MODE_DEPRECATED_ONLY"]
TierIssue = Literal["MARGIN_TABLE_MISSING", "MARGIN_TABLE_INVALID"]
Issue = CollateralIssue | ModeIssue | TierIssue | Literal["MARKET_DELISTED"]


class SourceEvidence(Evidence):
    model_config = ConfigDict(revalidate_instances="always", validate_default=True)


class SpotCollateral(SourceEvidence):
    network: Network
    index: TokenIndex
    token_id: str = Field(pattern=r"^0x[0-9a-f]{32}$")
    symbol: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    namespace: Literal["hyperliquid.spot"] = "hyperliquid.spot"
    observed_at: UtcDatetime
    canonical: bool | None = None

    @field_validator("canonical", mode="before")
    @classmethod
    def exact_flag(cls, value):
        return None if value is None else _strict_bool(value)

    @property
    def is_canonical_usdc(self) -> bool:
        return (self.index == 0 and self.symbol == "USDC" and self.canonical is True
                and (self.network != "MAINNET" or self.token_id == MAINNET_USDC_ID))

    def financial_unit(self) -> RiskFinancialUnit:
        return RiskFinancialUnit(network=self.network, kind="EXCHANGE_ASSET", symbol=self.symbol,
                                 asset_namespace=self.namespace, asset_reference=self.token_id,
                                 provenance="DECLARED_UNVERIFIED")


class MarginTier(SourceEvidence):
    lower_bound: LowerBound
    max_leverage: Leverage

    @field_validator("lower_bound")
    @classmethod
    def canonical_bound(cls, value):
        # Preserve exact input precision without depending on the active context.
        text = format(value, "f")
        return Decimal(text.rstrip("0").rstrip(".") if "." in text else text)


class ObservedMarginPolicy(SourceEvidence):
    mode: MarketMode
    reported_mode: str | None = Field(default=None, max_length=40)
    only_isolated: bool | None = None
    table_id: TableId | None = None
    reported_max_leverage: Leverage | None = None
    tier_source: Literal["EXPLICIT_TABLE", "DOCUMENTED_TABLE_ID"] | None = None
    tiers: tuple[MarginTier, ...] = Field(default=(), max_length=32)

    @field_validator("only_isolated", mode="before")
    @classmethod
    def exact_flag(cls, value):
        return None if value is None else _strict_bool(value)

    @model_validator(mode="after")
    def validate_tiers(self):
        if not self.tiers:
            if self.tier_source is not None:
                raise ValueError("missing margin tiers")
            return self
        if (self.table_id is None or self.tier_source is None or self.tiers[0].lower_bound != 0
                or self.tiers[0].max_leverage != self.reported_max_leverage
                or any(a.lower_bound >= b.lower_bound or a.max_leverage < b.max_leverage
                       for a, b in zip(self.tiers, self.tiers[1:]))):
            raise ValueError("contradictory margin tiers")
        if self.table_id < 50 and (len(self.tiers) != 1 or self.tiers[0].max_leverage != self.table_id):
            raise ValueError("invalid single-tier table ID")
        if self.tier_source == "DOCUMENTED_TABLE_ID" and self.table_id >= 50:
            raise ValueError("tiered table requires provider rows")
        return self


class DocumentedCoreUnits(SourceEvidence):
    """Product specification evidence bound to a supported Mainnet Core market."""

    source: Literal["HYPERLIQUID_CONTRACT_SPECIFICATIONS"] = "HYPERLIQUID_CONTRACT_SPECIFICATIONS"
    price_denomination: Literal["USDT"] = "USDT"
    pnl_unit: RiskFinancialUnit


class MarketFinancialObservation(SourceEvidence):
    schema_version: Literal["phase183b-v1"] = "phase183b-v1"
    source: Literal["HYPERLIQUID_INFO_META"] = "HYPERLIQUID_INFO_META"
    metadata: MarketUniverseMetadata
    metadata_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    collateral_token_index: TokenIndex | None = None
    collateral: SpotCollateral | None = None
    collateral_source: Literal["HYPERLIQUID_INFO_SPOT_META"] | None = None
    collateral_status: SourceStatus
    margin: ObservedMarginPolicy
    margin_status: SourceStatus
    issues: tuple[Issue, ...] = Field(max_length=5)
    price_quote_unit: None = None
    settlement_unit: None = None
    documented_units: DocumentedCoreUnits | None = None
    account_mode: Literal["UNKNOWN"] = "UNKNOWN"
    read_only: Literal[True] = True
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"

    _flags = field_validator("read_only", "execution_eligible", mode="before")(_strict_bool)

    @model_validator(mode="after")
    def validate_sources(self):
        if (self.metadata.observed_at is None or self.metadata.metadata_status != "EXCHANGE_VERIFIED"
                or self.metadata_fingerprint != self.metadata.fingerprint()):
            raise ValueError("financial observation needs official discovery evidence")
        if self.collateral is not None:
            if (self.collateral.network != self.metadata.identity.network
                    or self.collateral.index != self.collateral_token_index
                    or self.collateral_source != "HYPERLIQUID_INFO_SPOT_META"):
                raise ValueError("invalid collateral observation binding")
        elif self.collateral_source is not None or self.collateral_status == "SOURCE_OBSERVED":
            raise ValueError("missing collateral observation")
        if self.documented_units is not None and self.documented_units != _documented_core_units(self.metadata, self.collateral):
            raise ValueError("invalid documented unit binding")
        if self.margin_status == "SOURCE_OBSERVED" and (not self.margin.tiers or self.margin.mode == "UNKNOWN"):
            raise ValueError("missing margin observation")
        return self

    @property
    def identity(self):
        return self.metadata.identity

    def fingerprint(self) -> str:
        return stable_fingerprint(self)

    def valid_until(self, max_age_seconds: int) -> datetime:
        observed = self.metadata.observed_at
        if self.collateral is not None:
            observed = min(observed, self.collateral.observed_at)
        return observed + timedelta(seconds=max_age_seconds)

    def status_at(self, evaluated_at: datetime, max_age_seconds: int) -> SourceStatus:
        discovery = evaluate_discovery(self.metadata, evaluated_at=evaluated_at, max_age_seconds=max_age_seconds)
        if discovery.reason == "NOT_LISTED":
            return "UNSUPPORTED"
        if (not discovery.discovery_eligible or evaluated_at >= self.valid_until(max_age_seconds)
                or (self.collateral is not None and self.collateral.observed_at > evaluated_at)):
            return "STALE"
        if "UNSUPPORTED" in (self.collateral_status, self.margin_status):
            return "UNSUPPORTED"
        if "UNAVAILABLE" in (self.collateral_status, self.margin_status):
            return "UNAVAILABLE"
        return "SOURCE_OBSERVED"


def _wire_int(value, minimum, maximum):
    return value if type(value) is int and minimum <= value <= maximum else None


def normalize_spot_tokens(raw, *, network: Network, observed_at: datetime) -> dict[int, SpotCollateral]:
    if not isinstance(raw, dict) or raw.get("network", network) != network:
        raise ValueError("spot metadata network or shape mismatch")
    rows = raw.get("tokens")
    if not isinstance(rows, list) or len(rows) > 8192:
        raise ValueError("unsupported spot token registry")
    tokens = {}
    indexes = set()
    token_ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid spot token row")
        index = _wire_int(row.get("index"), 0, 2**31 - 1)
        token_id = row.get("tokenId")
        if index is None or index in indexes or not isinstance(token_id, str) or token_id in token_ids:
            raise ValueError("invalid or ambiguous spot token identity")
        indexes.add(index)
        token_ids.add(token_id)
        try:
            tokens[index] = SpotCollateral(network=network, index=index, token_id=token_id,
                                           symbol=row.get("name"), observed_at=observed_at, canonical=row.get("isCanonical"))
        except ValueError:
            # Unsupported display/ID formats cannot resolve this index.
            continue
    return tokens


def _tables(raw):
    values = raw.get("marginTables", [])
    if not isinstance(values, list) or len(values) > 1024:
        return None
    tables = {}
    for entry in values:
        if not isinstance(entry, list) or len(entry) != 2:
            return None
        table_id = _wire_int(entry[0], 1, 2**31 - 1)
        if table_id is None or table_id in tables:
            return None
        tables[table_id] = entry[1]
    return tables


def _normalize_policy(row, tables):
    raw_mode = row.get("marginMode")
    legacy = row.get("onlyIsolated")
    only_isolated = legacy if type(legacy) is bool else None
    mode, mode_issue = "UNKNOWN", None
    if isinstance(raw_mode, str) and raw_mode in ("strictIsolated", "noCross", "normal"):
        mode = {"strictIsolated": "STRICT_ISOLATED", "noCross": "NO_CROSS", "normal": "CROSS_ELIGIBLE"}[raw_mode]
    elif raw_mode is not None or (legacy is not None and only_isolated is None):
        mode_issue = "MARGIN_MODE_UNSUPPORTED"
    elif only_isolated is True:
        mode, mode_issue = "ISOLATED_UNSPECIFIED", "MARGIN_MODE_DEPRECATED_ONLY"
    else:
        mode_issue = "MARGIN_MODE_MISSING"

    table_id = _wire_int(row.get("marginTableId"), 1, 2**31 - 1)
    leverage = _wire_int(row.get("maxLeverage"), 1, 100)
    fields = dict(mode=mode, reported_mode=raw_mode if isinstance(raw_mode, str) and len(raw_mode) <= 40 else None,
                  only_isolated=only_isolated, table_id=table_id, reported_max_leverage=leverage)
    try:
        if tables is None or (table_id is None and "marginTableId" in row) or (leverage is None and "maxLeverage" in row):
            raise ValueError("invalid margin table identifiers")
        if table_id in tables:
            value = tables[table_id]
            rows = value.get("marginTiers") if isinstance(value, dict) else None
            if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
                raise ValueError("invalid margin tier table")
            tiers = tuple(MarginTier(lower_bound=t["lowerBound"], max_leverage=t["maxLeverage"]) for t in rows)
            return ObservedMarginPolicy(**fields, tiers=tiers, tier_source="EXPLICIT_TABLE"), mode_issue, None
        if table_id is not None and table_id < 50:
            tier = MarginTier(lower_bound=0, max_leverage=table_id)
            return ObservedMarginPolicy(**fields, tiers=(tier,), tier_source="DOCUMENTED_TABLE_ID"), mode_issue, None
    except (KeyError, TypeError, ValueError):
        return ObservedMarginPolicy(**fields), mode_issue, "MARGIN_TABLE_INVALID"
    return ObservedMarginPolicy(**fields), mode_issue, "MARGIN_TABLE_MISSING"


def _documented_core_units(record, collateral):
    identity = record.identity
    # The published Core crypto-perp specification distinguishes USDT oracle
    # denomination from USDC P&L. Bind only the native markets reviewed here.
    if (identity.network == "MAINNET" and identity.instrument_type == "CORE_PERP"
            and identity.instrument_name in {"BTC", "ETH", "SOL"} and record.listed
            and collateral is not None and collateral.is_canonical_usdc):
        return DocumentedCoreUnits(pnl_unit=collateral.financial_unit())
    return None


def normalize_financial_metadata(raw, records, spot_tokens):
    """Consume the exact namespace payload already validated against these discovery rows."""
    index = _wire_int(raw.get("collateralToken"), 0, 2**31 - 1)
    collateral = None
    if "collateralToken" not in raw:
        collateral_status, collateral_issue = "UNAVAILABLE", "COLLATERAL_MISSING"
    elif index is None:
        collateral_status, collateral_issue = "UNSUPPORTED", "COLLATERAL_INVALID"
    elif spot_tokens is None:
        collateral_status, collateral_issue = "UNAVAILABLE", "TOKEN_METADATA_UNAVAILABLE"
    elif (collateral := spot_tokens.get(index)) is None:
        collateral_status, collateral_issue = "UNSUPPORTED", "TOKEN_UNRESOLVED"
    else:
        collateral_status, collateral_issue = "SOURCE_OBSERVED", None

    tables = _tables(raw)
    for record in records:
        row = raw["universe"][record.universe_index]
        if row["name"] != record.source_coin or (collateral is not None and collateral.network != record.identity.network):
            raise ValueError("financial metadata source binding mismatch")
        margin, mode_issue, tier_issue = _normalize_policy(row, tables)
        if not record.listed or mode_issue == "MARGIN_MODE_UNSUPPORTED" or tier_issue == "MARGIN_TABLE_INVALID":
            margin_status = "UNSUPPORTED"
        elif mode_issue == "MARGIN_MODE_MISSING" or tier_issue is not None:
            margin_status = "UNAVAILABLE"
        else:
            margin_status = "SOURCE_OBSERVED"
        yield MarketFinancialObservation(
            metadata=record, metadata_fingerprint=record.fingerprint(),
            collateral_token_index=index, collateral=collateral,
            documented_units=_documented_core_units(record, collateral),
            collateral_source="HYPERLIQUID_INFO_SPOT_META" if collateral is not None else None,
            collateral_status=collateral_status, margin=margin, margin_status=margin_status,
            issues=tuple(issue for issue in (collateral_issue, mode_issue, tier_issue,
                                             None if record.listed else "MARKET_DELISTED") if issue),
        )
