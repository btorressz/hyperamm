import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Event

import httpx
import pytest
from pydantic import ValidationError

from app import main
from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
from app.market_data.market_universe_contracts import evaluate_discovery
from app.market_data.market_universe_discovery import MarketUniverseDiscovery, normalize_metadata
from app.simulation.engine import SimulationEngine
from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.generalized_market_profiles import (
    PROFILE_VERSION, GeneralizedMarketProfile, GeneralizedPaperResult, PaperAdmission,
    PaperProposal, PaperRejected, assess, execute_paper,
)
from app.simulation.market_profiles import round_level, validate_price
from app.simulation.scenarios import ScenarioName

URL = "/api/v1/generalized-paper"


def evidence(*, name="DOGE", dex="", precision=2, network="MAINNET", listed=True):
    row = {"name": f"{dex}:{name}" if dex else name, "szDecimals": precision, "isDelisted": not listed}
    record, = normalize_metadata({"universe": [row]}, network=network, dex=dex,
                                 observed_at=datetime.now(timezone.utc))
    return record


def proposal_for(record, *, price="0.1234", **overrides):
    return PaperProposal(profile_version=PROFILE_VERSION, identity=record.identity,
                         simulated_reference_price=price, **{
                             "frames": 12, "scenario": ScenarioName.QUIET,
                             "economics": {"model": "HYPOTHETICAL_LINEAR"}, **overrides,
                         })


def admit(record, proposal=None, **kwargs):
    return assess(proposal or proposal_for(record), record, **{
        "network": "MAINNET", "evaluated_at": record.observed_at, "max_age_seconds": 60, **kwargs,
    })


@pytest.mark.parametrize("scenario", list(ScenarioName))
def test_existing_scenarios_produce_ordered_positive_quantized_books(scenario):
    record = evidence(dex="xyz", name="GOLD", precision=3)
    proposal = proposal_for(record, price="999.99", scenario=scenario, frames=40,
                            economics={"model": "HYPOTHETICAL_LINEAR", "funding_interval_seconds": 1})
    admission, prepared = admit(record, proposal)
    assert admission.status == "ELIGIBLE"
    assert prepared.strategy.market == record.identity.stable_key
    assert len(prepared.dataset.frames) == 40
    for frame in prepared.dataset.frames:
        bids, asks = frame.market.book.bids, frame.market.book.asks
        assert len(bids) == len(asks) == 5 and bids[0].price < asks[0].price
        assert all(a.price > b.price for a, b in zip(bids, bids[1:]))
        assert all(a.price < b.price for a, b in zip(asks, asks[1:]))
        assert all(x.size > 0 and x.size == x.size.quantize(Decimal(".001")) and
                   validate_price(x.price, 3) for x in bids + asks)


@pytest.mark.parametrize(("precision", "price"), [
    (0, "0.001"), (1, "0.0123"), (2, "0.1234"), (3, "9.999"),
    (4, "99.99"), (5, "1000.1"), (6, "1000000"),
])
def test_supported_magnitudes_and_all_size_precisions(precision, price):
    record = evidence(precision=precision)
    p = proposal_for(record, price=price, scenario="HIGH_VOLATILITY", frames=120)
    admission, prepared = admit(record, p)
    assert admission.reason == "ADMITTED"
    qty = prepared.strategy
    assert qty.base_order_size * Decimal(price) <= p.minimum_order_notional
    assert qty.base_order_size * 4 <= qty.total_liquidity < qty.soft_inventory_limit_base < qty.hard_inventory_limit_base
    assert all(x.as_tuple().exponent == -precision for x in (
        qty.base_order_size, qty.total_liquidity, qty.soft_inventory_limit_base, qty.hard_inventory_limit_base,
    ))


@pytest.mark.parametrize(("price", "precision"), [("9.99999", 0), ("9999.9999", 2), ("999.991", 1), ("1000.01", 6)])
def test_price_transition_and_notional_conservation(price, precision):
    price = Decimal(price)
    quantity = Decimal("91.123456")
    bid, bid_size = round_level(price, quantity, precision, up=False)
    ask, ask_size = round_level(price, quantity, precision, up=True)
    assert bid <= price <= ask and bid < ask
    assert validate_price(bid, precision) and validate_price(ask, precision)
    assert 0 <= bid_size <= quantity and 0 <= ask_size <= quantity
    assert max(bid * bid_size, ask * ask_size) <= price * quantity


@pytest.mark.parametrize(("precision", "price", "settings", "reason"), [
    (6, "0.01", {}, "PRICE_UNREPRESENTABLE"),
    (1, "0.0032", {}, "PRICE_UNREPRESENTABLE"),
    (2, "0.12345", {}, "PRICE_UNREPRESENTABLE"),
    (0, "1000", {}, "SIZE_UNREPRESENTABLE"),
    (0, "100", {"synthetic_top_depth_quote": "1"}, "SIZE_UNREPRESENTABLE"),
    (0, "100", {"synthetic_top_depth_quote": "1200", "scenario": "LIQUIDITY_SHOCK"}, "SIZE_UNREPRESENTABLE"),
    (2, "0.1234", {"minimum_order_notional": "0.001"}, "SIZE_UNREPRESENTABLE"),
    (2, "0.1234", {"scenario": "NEGATIVE_FUNDING_STRESS"}, "FUNDING_MODEL_UNSUPPORTED"),
    (2, "0.1234", {"scenario": "FLASH_MOVE", "frames": 2}, "SCENARIO_INFEASIBLE"),
    (2, "0.1234", {"scenario": "LIQUIDITY_SHOCK", "frames": 4}, "SCENARIO_INFEASIBLE"),
    (2, "0.1234", {"scenario": "POSITIVE_FUNDING_STRESS",
                   "economics": {"model": "HYPOTHETICAL_LINEAR", "funding_interval_seconds": 12}},
     "FUNDING_MODEL_UNSUPPORTED"),
])
def test_invalid_precision_depth_inventory_or_funding_fails_preflight(precision, price, settings, reason):
    record = evidence(precision=precision)
    admission, prepared = admit(record, proposal_for(record, price=price, **settings))
    assert prepared is None and admission.reason == reason and admission.checks


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-1", "0", "1e99999", "0.0000000000001", 0.1, True])
def test_invalid_decimal_inputs_fail_before_calculation(price):
    with pytest.raises(ValidationError):
        proposal_for(evidence(), price=price)


def test_identity_and_fingerprint_boundaries():
    core, hip, other_dex, testnet = evidence(), evidence(dex="xyz"), evidence(dex="abc"), evidence(network="TESTNET")
    assert len({r.identity.stable_key for r in (core, hip, other_dex, testnet)}) == 4
    initial, _ = admit(core)
    refreshed, _ = admit(core.model_copy(update={"observed_at": core.observed_at + timedelta(seconds=1)}))
    assert initial.profile.profile_fingerprint == refreshed.profile.profile_fingerprint
    assert initial.binding.configuration_fingerprint == refreshed.binding.configuration_fingerprint
    assert initial.binding.metadata_fingerprint != refreshed.binding.metadata_fingerprint
    price, _ = admit(core, proposal_for(core, price="0.1235"))
    scenario, _ = admit(core, proposal_for(core, scenario="TREND_UP"))
    fees, _ = admit(core, proposal_for(core, economics={"model": "HYPOTHETICAL_LINEAR", "maker_fee_bps": "2"}))
    for changed in (price, fees):
        assert changed.profile.profile_fingerprint != initial.profile.profile_fingerprint
        assert changed.binding.configuration_fingerprint != initial.binding.configuration_fingerprint
    assert initial.profile.profile_fingerprint == scenario.profile.profile_fingerprint
    assert initial.binding.configuration_fingerprint != scenario.binding.configuration_fingerprint
    assert admit(hip, proposal_for(core))[0].reason == "IDENTITY_MISMATCH"
    assert admit(testnet)[0].reason == "NETWORK_MISMATCH"
    assert admit(testnet, network="TESTNET")[0].status == "ELIGIBLE"
    discovery = evaluate_discovery(core, evaluated_at=core.observed_at, max_age_seconds=60)
    assert discovery.discovery_eligible and not discovery.paper_research_eligible and not discovery.execution_eligible
    assert initial.profile.discovery == discovery and initial.profile.limitations == initial.limitations
    assert initial.authority == discovery.authority == "NONE" and not initial.execution_eligible


def test_failed_evidence_and_nested_mutations_fail_closed():
    record = evidence()
    admission, _ = admit(record)
    times = (record.observed_at + timedelta(seconds=61), record.observed_at - timedelta(seconds=1))
    assert all(admit(record, evaluated_at=when)[0].reason == "METADATA_STALE" for when in times)
    assert admit(record, metadata_current=False)[0].reason == "METADATA_STALE"
    assert admit(evidence(listed=False))[0].reason == "MARKET_DELISTED"
    fixture = record.model_copy(update={"metadata_status": "DEMO_PROFILE", "metadata_source": "PINNED_RESEARCH_FIXTURE",
                                        "listed": None, "source_coin": None, "universe_index": None, "observed_at": None})
    assert admit(fixture, evaluated_at=record.observed_at)[0].reason == "METADATA_UNAVAILABLE"
    for changes in (
        {"stable_key": "elsewhere"},
        {"profile_fingerprint": "a" * 64},
        {"discovery": admission.profile.discovery.model_copy(update={"paper_research_eligible": True})},
        {"limitations": ()},
        {"metadata": record.model_copy(update={"sz_decimals": 6})},
        {"economics": admission.profile.economics.model_copy(update={"maker_fee_bps": Decimal("NaN")})},
    ):
        with pytest.raises(ValidationError):
            GeneralizedMarketProfile.model_validate(admission.profile.model_copy(update=changes))
    for changes in ({"execution_eligible": True}, {"valid_until": record.observed_at - timedelta(seconds=1)}):
        with pytest.raises(ValidationError):
            PaperAdmission.model_validate(admission.model_copy(update=changes))


@pytest.mark.parametrize(("dex", "name", "precision", "price"), [("", "DOGE", 2, "0.1234"), ("xyz", "GOLD", 3, "2500")])
async def test_deterministic_core_hip3_fills_fee_funding_and_inventory(dex, name, precision, price):
    record = evidence(dex=dex, name=name, precision=precision)
    proposal = proposal_for(record, price=price, scenario="FLASH_MOVE", frames=40, trace_max_points=40,
                            economics={"model": "HYPOTHETICAL_LINEAR", "maker_fee_bps": "1",
                                       "taker_fee_bps": "3", "funding_interval_seconds": 1})
    admission, prepared = admit(record, proposal)

    async def run():
        return await execute_paper(SimulationEngine(), proposal=proposal, metadata=record,
                                   network="MAINNET", max_age_seconds=60, expected=admission.binding)

    a, b = await run(), await run()
    assert a.result_fingerprint == b.result_fingerprint and a.result == b.result
    result = GeneralizedPaperResult.model_validate_json(a.model_dump_json()).result
    assert result.metrics.fill_count >= 1 and result.dataset_fingerprint == prepared.dataset.fingerprint
    vault = result.vault
    assert vault.fees_quote > 0 and vault.funding_quote != 0
    assert vault.net_pnl_quote == vault.realized_pnl_quote + vault.unrealized_pnl_quote - vault.fees_quote + vault.funding_quote
    assert vault.equity_quote == vault.initial_equity_quote + vault.net_pnl_quote
    assert vault.position_base == sum(Decimal(fill["size"]) * (1 if fill["side"] == "BID" else -1)
                                      for fill in result.fills)
    with pytest.raises(ValidationError):
        GeneralizedPaperResult.model_validate(a.model_copy(update={"proposal": proposal.model_copy(
            update={"minimum_order_notional": Decimal("102")})}))
    for fill in result.fills:
        assert fill["market"] == record.identity.stable_key and fill["source"] == "SIMULATED PAPER FILL"
        assert Decimal(fill["size"]) > 0 and validate_price(Decimal(fill["price"]), precision)
    assert all(abs(x.inventory_base) <= prepared.strategy.hard_inventory_limit_base for x in result.trace)


@pytest.fixture
async def api_client(monkeypatch):
    now = datetime.now(timezone.utc)
    calls = []

    def provider(method, dex, deadline):
        calls.append((method, dex))
        if method == "perpDexs":
            return [None, {"name": "xyz"}]
        return {"universe": [{"name": "xyz:GOLD" if dex else "DOGE", "szDecimals": 2}]}

    service = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=provider, clock=lambda: now)
    executor = SimulationExecutor()
    monkeypatch.setattr(main.app.state, "market_universe_discovery", service, raising=False)
    monkeypatch.setattr(main.app.state, "simulation_executor", executor, raising=False)
    monkeypatch.delattr(main.app.state, "runtime", raising=False)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                    base_url="http://127.0.0.1") as client:
            yield client, service, executor, calls
    finally:
        await executor.shutdown()
        await service.close()


async def test_real_api_rejects_forged_and_expired_admission_before_dispatch(api_client, monkeypatch):
    client, service, executor, calls = api_client
    payload = proposal_for(evidence(), scenario="FLASH_MOVE").model_dump(mode="json")
    preview = await client.post(f"{URL}/eligibility", json=payload)
    assert preview.status_code == 200 and preview.headers["cache-control"] == "no-store"
    binding = PaperAdmission.model_validate_json(preview.content).binding.model_dump()
    assert set(calls) == {("perpDexs", ""), ("meta", ""), ("meta", "xyz")}

    async def no_dispatch(*args, **kwargs):
        pytest.fail("rejected request reached worker")
    monkeypatch.setattr(executor, "execute", no_dispatch)
    for key in binding:
        wrong = {**binding, key: "a" * 64}
        r = await client.post(f"{URL}/run", json={**payload, "expected": wrong})
        assert r.status_code == 409 and r.json()["reason"] == key.upper() + "_MISMATCH"
    for malformed in ({"execution_mode": "TESTNET"}, {"execution_eligible": True}, {"admission": preview.json()}):
        r = await client.post(f"{URL}/run", json={**payload, "expected": binding, **malformed})
        assert r.status_code == 422 and r.json()["reason"] == "CONFIGURATION_INVALID"
    unsupported = await client.post(f"{URL}/eligibility", json={**payload, "profile_version": "phase170-v1"})
    assert unsupported.status_code == 422 and unsupported.json()["reason"] == "PROFILE_UNSUPPORTED"
    absent = await client.post(f"{URL}/eligibility", json={k: v for k, v in payload.items() if k != "profile_version"})
    assert absent.status_code == 422 and absent.json()["reason"] == "PROFILE_UNSUPPORTED"
    assert (await client.post(f"{URL}/eligibility", content=b"x" * 65537)).status_code == 413
    for change in ({"simulated_reference_price": "0.12345"}, {"synthetic_top_depth_quote": "0.001"},
                   {"frames": 121}, {"simulated_reference_price": "NaN"}):
        assert (await client.post(f"{URL}/eligibility", json={**payload, **change})).status_code == 422
    service._clock = lambda now=service._clock(): now + timedelta(seconds=1)
    service._expires = 0.0
    refreshed = await client.post(f"{URL}/run", json={**payload, "expected": binding})
    assert refreshed.status_code == 409 and refreshed.json()["reason"] == "METADATA_FINGERPRINT_MISMATCH"
    service._clock = lambda now=service._clock(): now + timedelta(seconds=61)
    stale = await client.post(f"{URL}/run", json={**payload, "expected": binding})
    assert stale.status_code == 503 and stale.json()["reason"] == "METADATA_STALE"


async def test_real_api_runs_both_instruments_without_orders_or_signer(api_client, monkeypatch):
    from eth_account import Account
    from hyperliquid.exchange import Exchange

    def forbidden(*args, **kwargs):
        pytest.fail("PAPER reached an exchange adapter, order method or signer")
    monkeypatch.setattr(Exchange, "order", forbidden)
    monkeypatch.setattr(Exchange, "bulk_orders", forbidden)
    monkeypatch.setattr(Account, "from_key", forbidden)
    for method in ("__init__", "submit_orders", "replace_orders", "cancel_orders"):
        monkeypatch.setattr(HyperliquidTestnetExecutionAdapter, method, forbidden)
    client, _, _, _ = api_client
    for record, price in ((evidence(), "0.1234"), (evidence(dex="xyz", name="GOLD"), "2500")):
        data = proposal_for(record, price=price, frames=40, trace_max_points=5, scenario="FLASH_MOVE").model_dump(mode="json")
        preview = await client.post(f"{URL}/eligibility", json=data)
        assert preview.status_code == 200
        run = await client.post(f"{URL}/run", json={**data, "expected": preview.json()["binding"]})
        assert run.status_code == 200, run.text
        assert len(run.content) < 2_000_000 and run.headers["cache-control"] == "no-store"
        value = GeneralizedPaperResult.model_validate_json(run.content)
        assert value.admission.identity == record.identity and len(value.result.trace) == 5
        assert value.result.vault.fees_quote == value.result.vault.funding_quote == 0


async def test_worker_retains_capacity_after_generalized_waiter_cancels(monkeypatch):
    record = evidence()
    p = proposal_for(record)
    admission, _ = admit(record, p)
    started, release = Event(), Event()
    original = SimulationEngine.run

    async def slow_engine(self, **kwargs):
        started.set()
        assert await asyncio.to_thread(release.wait, 5)
        return await original(self, **kwargs)
    monkeypatch.setattr(SimulationEngine, "run", slow_engine)
    executor = SimulationExecutor()
    args = dict(proposal=p, metadata=record, network="MAINNET", max_age_seconds=60, expected=admission.binding)
    try:
        task = asyncio.create_task(executor.execute("run_generalized_paper", **args))
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ResearchBusyError):
            await executor.execute("run_scenario")
    finally:
        release.set()
        await executor.shutdown()
    assert not executor._busy


async def test_worker_rejects_snapshot_that_expired_between_api_and_start(monkeypatch):
    record = evidence()
    record = record.model_copy(update={"observed_at": record.observed_at - timedelta(seconds=61)})
    proposal = proposal_for(record)
    preview, _ = admit(record, proposal)
    assert preview.status == "ELIGIBLE"
    async def must_not_start(*args, **kwargs):
        pytest.fail("expired admission reached the simulation engine")
    monkeypatch.setattr(SimulationEngine, "run", must_not_start)
    with pytest.raises(PaperRejected) as rejected:
        await execute_paper(SimulationEngine(), proposal=proposal, metadata=record, network="MAINNET",
                            max_age_seconds=60, expected=preview.binding)
    assert rejected.value.admission.reason == "METADATA_STALE"
