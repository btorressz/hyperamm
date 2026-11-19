import asyncio
import json
from datetime import datetime, timedelta, timezone
from time import monotonic

import pytest

from app.market_data.market_risk_metadata import normalize_financial_metadata, normalize_spot_tokens
from app.market_data.market_universe_discovery import (
    DiscoveryFailure, MarketUniverseDiscovery, OfficialMetadataClient, normalize_metadata,
)
from test_phase181_market_discovery import WireResponse, wire  # noqa: F401

NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
USDC = "0x6d1e7cde53ba9467b783cb7c530ce054"
OTHER = "0x00000000000000000000000000000002"


def spot_wire():
    return {"tokens": [
        {"index": 0, "tokenId": USDC, "name": "USDC", "isCanonical": True},
        {"index": 268, "tokenId": OTHER, "name": "USDC"},
    ]}


def tier(bound, leverage):
    return {"lowerBound": bound, "maxLeverage": leverage}


def market_wire(dex="", *, coin=None, index=0, mode="strictIsolated", table=10, leverage=10, tiers=None):
    row = {"name": coin or (f"{dex}:GOLD" if dex else "BTC"), "szDecimals": 3,
           "maxLeverage": leverage, "marginTableId": table}
    if mode is not None:
        row.update(marginMode=mode, onlyIsolated=True)
    payload = {"universe": [row], "collateralToken": index}
    if tiers is not None:
        payload["marginTables"] = [[table, {"marginTiers": tiers}]]
    return payload


def observation(*, dex="", network="MAINNET", raw=None, tokens=None, now=NOW):
    raw = market_wire(dex) if raw is None else raw
    metadata = normalize_metadata(raw, network=network, dex=dex, observed_at=now)
    if tokens is None:
        tokens = normalize_spot_tokens(spot_wire(), network=network, observed_at=now)
    result, = normalize_financial_metadata(raw, metadata, tokens)
    return result


def test_core_hip3_asset_binding_preserves_same_symbol_distinct_identity_and_network():
    core = observation(raw=market_wire(table=56, tiers=[tier("0", 10), tier("1000.00", 5)]))
    hip = observation(dex="xyz", raw=market_wire("xyz", index=268, mode="noCross"))
    separate_network = observation(network="TESTNET")
    assert core.collateral.symbol == hip.collateral.symbol
    assert core.collateral.financial_unit() != hip.collateral.financial_unit()
    assert core.collateral.financial_unit() != separate_network.collateral.financial_unit()
    assert (core.identity.dex, hip.identity.dex, hip.collateral_token_index) == ("", "xyz", 268)
    assert (core.margin.mode, hip.margin.mode) == ("STRICT_ISOLATED", "NO_CROSS")
    assert (core.margin.tier_source, hip.margin.tier_source) == ("EXPLICIT_TABLE", "DOCUMENTED_TABLE_ID")
    assert core.status_at(NOW, 60) == hip.status_at(NOW, 60) == "SOURCE_OBSERVED"
    assert core.price_quote_unit is core.settlement_unit is None
    assert core.account_mode == "UNKNOWN" and core.authority == "NONE"
    assert not core.execution_eligible


@pytest.mark.parametrize(("mutation", "reason", "status"), [
    (lambda raw: raw.pop("collateralToken"), "COLLATERAL_MISSING", "UNAVAILABLE"),
    (lambda raw: raw.update(collateralToken=True), "COLLATERAL_INVALID", "UNSUPPORTED"),
    (lambda raw: raw.update(collateralToken=1000), "TOKEN_UNRESOLVED", "UNSUPPORTED"),
    (lambda raw: raw["universe"][0].update(marginMode="newMode"), "MARGIN_MODE_UNSUPPORTED", "UNSUPPORTED"),
    (lambda raw: raw["universe"][0].update(marginTableId=60), "MARGIN_TABLE_MISSING", "UNAVAILABLE"),
    (lambda raw: raw["universe"][0].update(maxLeverage=101), "MARGIN_TABLE_INVALID", "UNSUPPORTED"),
    (lambda raw: raw["universe"][0].update(isDelisted=True), "MARKET_DELISTED", "UNSUPPORTED"),
])
def test_missing_or_unsupported_metadata_is_explicit(mutation, reason, status):
    raw = market_wire()
    mutation(raw)
    result = observation(raw=raw)
    assert reason in result.issues and result.status_at(NOW, 60) == status


def test_mode_missing_and_deprecated_are_distinct_and_explicit_takes_priority():
    missing = observation(raw=market_wire(mode=None))
    assert missing.status_at(NOW, 60) == "UNAVAILABLE"
    assert missing.margin.mode == "UNKNOWN" and "MARGIN_MODE_MISSING" in missing.issues
    raw = market_wire(mode=None)
    raw["universe"][0]["onlyIsolated"] = True
    older = observation(raw=raw)
    assert older.margin.mode == "ISOLATED_UNSPECIFIED"
    assert "MARGIN_MODE_DEPRECATED_ONLY" in older.issues
    raw["universe"][0].update(marginMode="noCross", onlyIsolated=False)
    result = observation(raw=raw)
    assert result.margin.mode == "NO_CROSS" and result.margin.only_isolated is False


@pytest.mark.parametrize("tiers", [
    [tier("1", 10)], [tier("0", 5)], [tier("0", 10), tier("0", 5)],
    [tier("0", 10), tier("100", 11)], [tier("0", 10), tier("-100", 5)],
    [tier(0.0, 10)], [tier("0", True)], [tier("0", 10), tier("NaN", 5)],
    [tier("0", 10), tier("100", 5), tier("90", 3)],
])
def test_invalid_tiers_cannot_be_used(tiers):
    result = observation(raw=market_wire(table=56, tiers=tiers))
    assert result.margin.tiers == () and result.issues == ("MARGIN_TABLE_INVALID",)


def test_documented_core_pricing_and_pnl_remain_distinct_from_collateral_observation():
    tokens = normalize_spot_tokens({"tokens": [{"index": 0, "tokenId": "0x6d1e7cde53ba9467b783cb7c530ce054",
                                               "name": "USDC", "isCanonical": True}]},
                                  network="MAINNET", observed_at=NOW)
    core = observation(tokens=tokens)
    hip = observation(dex="xyz", tokens=tokens)
    assert core.documented_units.price_denomination == "USDT"
    assert core.documented_units.pnl_unit == core.collateral.financial_unit()
    assert core.price_quote_unit is core.settlement_unit is None
    assert hip.documented_units is None
    assert observation(raw=market_wire(mode="normal")).margin.mode == "CROSS_ELIGIBLE"


def test_ambiguous_registry_and_cross_network_resolution_reject():
    raw = spot_wire()
    raw["tokens"][1]["index"] = 0
    with pytest.raises(ValueError):
        normalize_spot_tokens(raw, network="MAINNET", observed_at=NOW)
    raw = spot_wire()
    raw["tokens"][1]["tokenId"] = USDC
    with pytest.raises(ValueError):
        normalize_spot_tokens(raw, network="MAINNET", observed_at=NOW)
    with pytest.raises(ValueError):
        normalize_spot_tokens({"network": "TESTNET", **spot_wire()}, network="MAINNET", observed_at=NOW)
    tokens = normalize_spot_tokens(spot_wire(), network="TESTNET", observed_at=NOW)
    with pytest.raises(ValueError, match="binding"):
        observation(tokens=tokens)


def test_expiry_future_and_material_fingerprints():
    first = observation(raw=market_wire(table=56, tiers=[tier("0.0", 10), tier("100.00", 5)]))
    equivalent = observation(raw=market_wire(table=56, tiers=[tier("0", 10), tier("100", 5)]))
    changed = observation(raw=market_wire(table=56, tiers=[tier("0", 10), tier("100", 4)]))
    assert first.fingerprint() == equivalent.fingerprint() != changed.fingerprint()
    assert first.status_at(NOW - timedelta(microseconds=1), 60) == "STALE"
    assert first.status_at(NOW + timedelta(seconds=60), 60) == "STALE"


def test_spot_sdk_uses_only_public_payload_and_closes_session(wire):
    requests, responses, sessions = wire
    responses[0] = WireResponse(body=json.dumps(spot_wire()).encode())
    assert OfficialMetadataClient("MAINNET")("spotMeta", "", monotonic() + 5) == spot_wire()
    assert len(requests) == len(sessions) == 1 and responses == []
    assert json.loads(requests[0][0].body) == {"type": "spotMeta"}
    assert requests[0][0].url == "https://api.hyperliquid.xyz/info"


@pytest.mark.parametrize("failure", [None, "RATE_LIMITED", "INVALID_DATA", "PARTIAL_DEX"])
async def test_single_flight_spot_resolution_and_partial_failure(failure):
    calls = []

    def provider(method, dex, deadline):
        calls.append((method, dex))
        if method == "perpDexs":
            return [None, {"name": "xyz"}]
        if method == "spotMeta":
            if failure == "RATE_LIMITED":
                raise DiscoveryFailure("RATE_LIMITED")
            return [] if failure == "INVALID_DATA" else spot_wire()
        if dex and failure == "PARTIAL_DEX":
            raise DiscoveryFailure("UPSTREAM_ERROR")
        return market_wire(dex, index=268 if dex else 0)

    service = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=provider, cache_seconds=1)
    try:
        first, second = await asyncio.gather(service.catalog(), service.catalog())
        assert first.catalog_fingerprint == second.catalog_fingerprint
        assert calls.count(("spotMeta", "")) == 1
        if failure == "PARTIAL_DEX":
            assert first.availability == "PARTIAL" and first.catalog is None
            assert service.paper_generation(first.catalog_fingerprint) is None
        else:
            assert first.availability == "AVAILABLE"
            for row in first.catalog.records:
                evidence = service.financial_observation(first.catalog_fingerprint, row.identity)
                assert evidence.status_at(first.evaluated_at, 1) == ("UNAVAILABLE" if failure else "SOURCE_OBSERVED")
                if failure:
                    assert "TOKEN_METADATA_UNAVAILABLE" in evidence.issues
            if failure == "RATE_LIMITED":
                assert service._refresh_result.rate_limited
    finally:
        await service.close()
    assert service.paper_generation(first.catalog_fingerprint) is None
