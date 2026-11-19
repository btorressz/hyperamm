"""Route-level financial evidence, admission binding and independent financial checks."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from threading import Event

import httpx
import pytest

from app import main
from app.market_data.market_risk_metadata import normalize_spot_tokens
from app.market_data.market_universe_discovery import MarketUniverseDiscovery
from app.risk.market_risk_engine import ResearchRiskSettings
from app.simulation.engine import SimulationEngine
from app.simulation.executor import SimulationExecutor
from test_phase182_generalized_paper import URL, proposal_for
from test_phase183b_market_risk_metadata import OTHER, USDC, market_wire, observation, spot_wire, tier
from test_phase183c_market_risk_calculations import bind, evaluate, sourced
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401

EVIDENCE = "/api/v1/market-universe/risk-evidence"


def target(catalog, record):
    return dict(network=record.identity.network, instrument_type=record.identity.instrument_type,
                dex=record.identity.dex, instrument_name=record.identity.instrument_name,
                catalog_fingerprint=catalog.catalog_fingerprint)


@pytest.fixture
async def risk_api(monkeypatch, offline_boundaries):
    clock = [datetime.now(timezone.utc)]
    calls = []

    def provider(method, dex, deadline):
        calls.append((method, dex))
        if method == "perpDexs":
            return [None, {"name": "xyz"}, {"name": "other"}, {"name": "missing"}]
        if method == "spotMeta":
            return spot_wire()
        if dex == "missing":
            payload = market_wire(dex)
            del payload["collateralToken"]
            return payload
        if dex == "other":
            return market_wire(dex, table=56, tiers=[tier("0", 10), tier("200", 5)])
        return market_wire(dex, index=268 if dex else 0, mode="noCross" if dex else "strictIsolated")

    source = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=provider, clock=lambda: clock[0])
    worker = SimulationExecutor()
    monkeypatch.setattr(main.app.state, "market_universe_discovery", source, raising=False)
    monkeypatch.setattr(main.app.state, "simulation_executor", worker, raising=False)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://localhost") as client:
            yield client, source, clock, calls
    finally:
        await worker.shutdown()
        await source.close()


async def test_shared_generation_readonly_evidence_and_real_worker(risk_api):
    client, source, _, calls = risk_api
    catalog = await source.catalog()
    records = {record.identity.dex: record for record in catalog.catalog.records}
    core, hip, missing, unsupported = await asyncio.gather(*(
        client.get(EVIDENCE, params=target(catalog, records[dex])) for dex in ("", "xyz", "missing", "other")
    ))
    assert all(response.status_code == 200 for response in (core, hip, missing, unsupported)), core.text
    assert all(response.headers["cache-control"] == "no-store" for response in (core, hip, missing, unsupported))
    core, hip, missing, unsupported = (response.json() for response in (core, hip, missing, unsupported))
    for wire, token, modes, dex in ((core, USDC, ["ISOLATED", "STRICT_ISOLATED"], ""),
                                    (hip, OTHER, ["ISOLATED", "NO_CROSS"], "xyz")):
        assert wire["schema_version"] == "phase183e-v1" and wire["model_version"] == "phase183c-v1"
        assert wire["identity"]["dex"] == dex and wire["identity"]["network"] == "MAINNET"
        assert wire["scope"] == "LOCAL_PAPER_ONLY" and wire["authority"] == "NONE"
        assert wire["read_only"] and not wire["execution_eligible"]
        assert wire["status"] == "SOURCE_OBSERVED" and wire["source_constraint_reason"] is None
        assert wire["source_margin_modes"] == modes
        assert wire["observation"]["collateral"]["token_id"] == token
        assert wire["observation"]["price_quote_unit"] is wire["observation"]["settlement_unit"] is None
        assert wire["observation"]["account_mode"] == "UNKNOWN"
    assert missing["status"] == "UNAVAILABLE" and missing["source_margin_modes"] == []
    assert missing["observation"]["issues"] == ["COLLATERAL_MISSING"]
    assert unsupported["status"] == "SOURCE_OBSERVED" and unsupported["source_margin_modes"] == []
    assert unsupported["source_constraint_reason"] == "RISK_SOURCE_UNSUPPORTED"
    assert calls.count(("spotMeta", "")) == calls.count(("perpDexs", "")) == 1
    assert len(calls) == 6

    record = records["xyz"]
    observed = source.financial_observation(catalog.catalog_fingerprint, record.identity)
    proposal = proposal_for(record, price="100", frames=5, research_risk=sourced(observed)).model_dump(mode="json")
    check = await client.post(URL + "/eligibility", json=proposal)
    assert check.status_code == 200, check.text
    admission = check.json()
    assert admission["risk_model"]["source_fingerprint"] == hip["source_fingerprint"]
    payload = {**proposal, "expected": admission["binding"]}
    result = await client.post(URL + "/run", json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["research_risk"]["model_fingerprint"] == admission["binding"]["research_risk_fingerprint"]

    for flag, value in (("authority", "MAINNET"), ("authority", "TESTNET"), ("execution_eligible", True),
                        ("risk_ready", True), ("exchange_margin_verified", True), ("shared_capital_eligible", True),
                        ("cross_market_netting_eligible", True)):
        forged = {**payload, "research_risk": {**payload["research_risk"], flag: value}}
        response = await client.post(URL + "/run", json=forged)
        assert response.status_code == 422 and response.json()["reason"] == "CONFIGURATION_INVALID"
    forged = {**payload, "expected": {**payload["expected"], "research_risk_fingerprint": "a" * 64}}
    response = await client.post(URL + "/run", json=forged)
    assert response.status_code == 409 and response.json()["reason"] == "RISK_FINGERPRINT_MISMATCH"
    for wrong in ({"asset_reference": USDC}, {"network": "TESTNET"}):
        settings = proposal["research_risk"]
        valuation = settings["valuation"]
        forged = {**proposal, "research_risk": {**settings, "valuation": {
            **valuation, "collateral_unit": {**valuation["collateral_unit"], **wrong}}}}
        response = await client.post(URL + "/eligibility", json=forged)
        assert response.status_code == 422 and response.json()["reason"] == "RISK_UNIT_MISMATCH"


async def test_lookup_rejects_cross_catalog_identity_and_expired_source(risk_api):
    client, discovery, clock, _ = risk_api
    catalog = await discovery.catalog()
    record = next(record for record in catalog.catalog.records if record.identity.dex == "xyz")
    selection = target(catalog, record)
    for change, status in (({"network": "TESTNET"}, 409), ({"catalog_fingerprint": "f" * 64}, 409),
                           ({"dex": "absent"}, 404), ({"dex": ""}, 422), ({"dex": "x" * 33}, 422),
                           ({"execution_eligible": "true"}, 422)):
        answer = await client.get(EVIDENCE, params={**selection, **change})
        assert answer.status_code == status and "observation" not in answer.json()
    clock[0] += timedelta(seconds=61)
    answer = await client.get(EVIDENCE, params=selection)
    assert answer.status_code == 409 and "observation" not in answer.json()


async def test_replaced_generation_retires_old_admission_and_preserves_started_capture(risk_api, monkeypatch):
    client, discovery, clock, calls = risk_api
    catalog = await discovery.catalog()
    record = next(record for record in catalog.catalog.records if record.identity.dex == "xyz")
    captured = discovery.financial_observation(catalog.catalog_fingerprint, record.identity)
    proposal = proposal_for(record, price="100", frames=5, research_risk=sourced(captured)).model_dump(mode="json")
    admission = (await client.post(URL + "/eligibility", json=proposal)).json()
    body = {**proposal, "expected": admission["binding"]}
    started, release = Event(), Event()
    original_run = SimulationEngine.run

    async def wait_for_refresh(self, **kwargs):
        started.set()
        assert await asyncio.to_thread(release.wait, 10)
        return await original_run(self, **kwargs)

    monkeypatch.setattr(SimulationEngine, "run", wait_for_refresh)
    running = asyncio.create_task(client.post(URL + "/run", json=body))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        clock[0] += timedelta(seconds=1)
        discovery._expires = 0  # Advance refresh scheduling without waiting for the provider TTL.
        current, stale = await asyncio.gather(discovery.catalog(), client.get(EVIDENCE, params=target(catalog, record)))
        assert current.catalog_fingerprint != catalog.catalog_fingerprint
        assert calls.count(("spotMeta", "")) == calls.count(("perpDexs", "")) == 2
        assert stale.status_code == 409
        rejected = await client.post(URL + "/run", json=body)
        assert rejected.status_code == 409 and rejected.json()["reason"] == "METADATA_FINGERPRINT_MISMATCH"
    finally:
        release.set()
        answer = await running
    assert answer.status_code == 200, answer.text
    completed = answer.json()["admission"]
    assert completed["binding"] == admission["binding"]
    assert completed["risk_model"]["source_fingerprint"] == captured.fingerprint()


def test_provider_symbol_cannot_alias_the_reserved_paper_accounting_unit():
    now = datetime.now(timezone.utc)
    payload = spot_wire()
    payload["tokens"][0]["name"] = "HYPOTHETICAL_QUOTE"
    registry = normalize_spot_tokens(payload, network="MAINNET", observed_at=now)
    source = observation(tokens=registry, now=now)
    assert source.collateral is None
    assert source.collateral_status == "UNSUPPORTED"
    assert source.issues == ("TOKEN_UNRESOLVED",)


@pytest.mark.parametrize("offset", ["-0.00000001", "0", "0.00000001"])
def test_exact_tier_boundary_against_continuous_deduction_formula(offset):
    source = observation(raw=market_wire(table=56, tiers=[tier("0", 10), tier("1000", 5), tier("2000", 3)]))
    model = bind(sourced(source, leverage="3"), source=source)
    notional = Decimal("2000") + Decimal(offset)
    result = evaluate(model, mark="1", position=str(notional), position_limit="10000")
    n = Fraction(notional)
    rate_prior, rate_next = Fraction(1, 10), Fraction(1, 6)
    deduction_prior = (rate_prior - Fraction(1, 20)) * 1000
    deduction_next = deduction_prior + (rate_next - rate_prior) * 2000
    exact = n * rate_prior - deduction_prior if n < 2000 else n * rate_next - deduction_next
    rounded = Fraction(result.margin.current.maintenance)
    assert exact <= rounded < exact + Fraction(1, 10**8)
    assert result.margin.current.tier_lower_bound == (1000 if n < 2000 else 2000)


@pytest.mark.parametrize("invalid_rate", ["0", "-1", "1000000.000000000001", 0.1, "NaN"])
def test_conversion_bounds_cannot_mint_capital(invalid_rate):
    source = observation()
    settings = sourced(source).model_dump()
    settings["valuation"]["collateral_per_paper_quote"] = invalid_rate
    with pytest.raises(ValueError):
        ResearchRiskSettings.model_validate(settings)
