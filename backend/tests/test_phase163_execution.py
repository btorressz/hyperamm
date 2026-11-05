"""Adversarial acceptance using the existing PAPER, accounting and replay worker."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D
import json
from threading import Event

import httpx
import pytest
from pydantic import ValidationError

from app.accounting import AccountingConfig, AccountingService
from app.amm.models import QuoteLevel
from app.execution.models import OrderRequest
from app.execution.order_manager import OrderManager
from app.execution.paper import PaperExecutionAdapter
from app.execution.research import PaperExecutionAssumptions
from app.market_data.models import MarketLevel, MarketSnapshot, OrderBookSnapshot
from app.research_replay.contracts import HistoricalReplayRequest, HistoricalReplayResult, ReplayRejected
from app.research_replay.validation import validate_bytes
from app.simulation.config import SimulationConfig
from app.simulation.engine import SimulationClock, SimulationEngine
from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.models import stable_fingerprint
from app.simulation.service import SimulationService
from app.simulation.scenarios import generate_scenario
from app.agents.config import AgentConfig
from app.risk.firewall import RiskFirewallConfig
from app.strategy.models import StrategyConfig
from test_phase162_replay import capture, inputs, request_for, vault
from test_phase161a_contracts import T


def assumptions(**changes):
    return PaperExecutionAssumptions(mode="MODELED_CROSSING", **changes)


def book(clock, market="BTC", *, bid="99", ask="101", size="0.3", sequence=1):
    return MarketSnapshot(market=market, best_bid=D(bid), best_ask=D(ask), stale=False,
        mid_price=(D(bid) + D(ask)) / 2, latest_valid_update=clock(),
        book=OrderBookSnapshot(market=market, timestamp=clock(), sequence=sequence,
            bids=[MarketLevel(price=D(bid), size=D(size)), MarketLevel(price=D(bid)-1, size=D(size))],
            asks=[MarketLevel(price=D(ask), size=D(size)), MarketLevel(price=D(ask)+1, size=D(size))]))


def order(cid="order", market="BTC", side="BID", price="110", size="1"):
    return OrderRequest(client_order_id=cid, market=market, side=side, price=D(price), size=D(size), level_index=0)


def args_for(vault, dataset, **controls):
    args = inputs(vault, dataset)
    payload = args["request"].model_dump(mode="json")
    payload["execution"]["paper"] = assumptions(**controls).model_dump(mode="json")
    args["request"] = HistoricalReplayRequest.model_validate(payload)
    return args


@pytest.mark.parametrize("field,value", [
    ("version", "phase163-v2"), ("mode", "PASSIVE"), ("queue_position", 1),
    ("order_latency_ms", True), ("order_latency_ms", 0.1), ("order_latency_ms", "1"),
    ("order_latency_ms", -1), ("order_latency_ms", 60001),
    ("cancel_latency_ms", -1), ("cancel_latency_ms", 60001), ("cancel_latency_ms", False),
    ("slippage_bps", 0.1), ("slippage_bps", True), ("slippage_bps", "NaN"),
    ("slippage_bps", "Infinity"), ("slippage_bps", "1e10000"), ("slippage_bps", "1001"),
    ("slippage_bps", "0.0000000000000000001"), ("participation_rate", "1.01"),
    ("participation_rate", -1), ("participation_rate", 0.5), ("max_fill_fraction", "-0.1"),
    ("max_fill_fraction", "1.1"), ("depth_sensitive", "true"), ("allow_partial_fills", 1),
])
def test_strict_bounded_versioned_assumptions(field, value):
    with pytest.raises(ValidationError):
        PaperExecutionAssumptions.model_validate({"mode": "MODELED_CROSSING", field: value})


@pytest.mark.parametrize("control", [dict(order_latency_ms=1), dict(cancel_latency_ms=1),
    dict(slippage_bps="1"), dict(depth_sensitive=True), dict(allow_partial_fills=False),
    dict(participation_rate="0"), dict(max_fill_fraction="0.5")])
def test_baseline_rejects_inactive_model_controls(control):
    with pytest.raises(ValidationError):
        PaperExecutionAssumptions(**control)


def test_fingerprint_reproduction_and_immutability():
    a = assumptions(slippage_bps="0.10", participation_rate="0.50")
    b = assumptions(slippage_bps="0.1", participation_rate="0.5")
    assert a.fingerprint == b.fingerprint
    assert PaperExecutionAssumptions.model_validate_json(a.model_dump_json()).fingerprint == a.fingerprint
    for field, value in dict(order_latency_ms=1, cancel_latency_ms=1, slippage_bps="1",
            depth_sensitive=True, allow_partial_fills=False, participation_rate="0", max_fill_fraction="0").items():
        assert assumptions(**{field: value}).fingerprint != assumptions().fingerprint
    with pytest.raises(ValidationError):
        a.order_latency_ms = 1
    with pytest.raises(ValidationError):
        PaperExecutionAdapter(assumptions=a.model_copy(update={"order_latency_ms": -1}))


@pytest.mark.parametrize("market", ["BTC", "ETH", "SOL"])
@pytest.mark.parametrize("side", ["BID", "ASK"])
@pytest.mark.parametrize("depth", [False, True])
async def test_observed_depth_prices_partial_fills_and_exact_accounting(market, side, depth):
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(depth_sensitive=depth, slippage_bps="10"))
    acct = AccountingService(market, clock=clock, config=AccountingConfig(paper_fee_model_enabled=True,
        paper_taker_fee_bps=D("3"), paper_funding_accounting_enabled=True, paper_funding_interval_seconds=1))
    def consume(fill):
        acct.ingest_fill(fill)
        acct.observe_execution_fills(paper.fills.all())
        assert paper.fills.acknowledge(fill, acct, agent_consumed=True)
    paper.on_fill = consume
    snapshot = book(clock, market)
    original = snapshot.model_dump_json()
    paper.update_market(snapshot)
    result = (await paper.submit_orders([order(market=market, side=side, price="110" if side == "BID" else "90")]))[0]
    assert result.status == "PARTIALLY_FILLED"
    assert result.filled_size == (D("0.6") if depth else D("0.3"))
    fills = paper.fills.all()
    expected = [D("101.101"), D("102.102")] if side == "BID" else [D("98.901"), D("97.902")]
    assert [f.price for f in fills] == expected[:2 if depth else 1]
    assert len({acct.fill_identity(f) for f in fills}) == len(fills)
    assert all(f.liquidity == "TAKER" and "HYPOTHETICAL" in f.source for f in fills)
    acct.mark(D("100"), observed_at=clock())
    state = acct.snapshot()
    notional = sum((f.price*f.size for f in fills), D(0))
    assert state.fees_quote == notional * D("0.0003")
    assert state.position_base == result.filled_size * (1 if side == "BID" else -1)
    assert state.net_pnl_quote == state.gross_pnl_quote - state.fees_quote + state.funding_quote
    assert state.equity_quote == state.initial_equity_quote + state.net_pnl_quote
    assert state.execution_accounting.execution_accounting_consistent
    assert acct.error is None
    assert len(acct.ledger.entries(100)) == len(fills)*2
    paper.update_market(snapshot)
    assert len(paper.fills.all()) == len(fills)
    assert snapshot.model_dump_json() == original


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("fraction", ["0", "0.5", "1"])
async def test_partial_switch_fraction_and_no_double_consumption(partial, fraction):
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(allow_partial_fills=partial,
        max_fill_fraction=fraction, participation_rate="0.5"))
    paper.update_market(book(clock, size="1"))
    rows = await paper.submit_orders([order("a"), order("b")])
    expected = D("0.5") if partial and D(fraction) > 0 else D(0)
    assert rows[0].filled_size == expected and rows[1].filled_size == 0
    for _ in range(3):
        paper.update_market(book(clock, size="1"))
    assert sum((f.size for f in paper.fills.all()), D(0)) == expected


@pytest.mark.parametrize("side,price", [("BID", "101"), ("ASK", "99")])
async def test_adverse_slippage_never_violates_limit(side, price):
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(slippage_bps="1"))
    paper.update_market(book(clock))
    row = (await paper.submit_orders([order(side=side, price=price)]))[0]
    assert row.filled_size == 0 and paper.fills.all() == []


@pytest.mark.parametrize("bad", ["absent", "stale", "bbo", "unsorted", "size", "market", "future"])
async def test_missing_or_inconsistent_book_never_infers_liquidity(bad):
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(depth_sensitive=True))
    snapshot = book(clock)
    if bad == "absent": snapshot.book = None
    if bad == "stale": snapshot.stale = True
    if bad == "bbo": snapshot.best_ask = D("100")
    if bad == "unsorted": snapshot.book.asks.reverse()
    if bad == "size": snapshot.book.asks[0].size = D("NaN")
    if bad == "market": snapshot.book.market = "DOGE"
    if bad == "future": snapshot.book.timestamp += timedelta(seconds=1)
    paper.update_market(snapshot)
    await paper.submit_orders([order()])
    assert paper.fills.all() == []


@pytest.mark.parametrize("elapsed,expected", [(999, "OPEN"), (1000, "FILLED"), (1001, "FILLED")])
async def test_order_latency_time_ties_and_no_interpolation(elapsed, expected):
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(order_latency_ms=1000))
    paper.update_market(book(clock, size="10"))
    row = (await paper.submit_orders([order()]))[0]
    assert row.status == "OPEN"
    clock.set(T + timedelta(milliseconds=elapsed))
    paper.update_market(book(clock, size="10", sequence=2))
    assert row.status == expected
    if paper.fills.all(): assert paper.fills.all()[0].timestamp == clock()


async def test_carried_book_cannot_fill_after_latency_or_replenish_on_context_frame():
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(order_latency_ms=1))
    snapshot = book(clock, size="10")
    paper.update_market(snapshot, evidence_key="original", evidence_at=T)
    row = (await paper.submit_orders([order()]))[0]
    clock.set(T + timedelta(seconds=1))
    paper.update_market(snapshot, evidence_key="original", evidence_at=T)
    assert row.filled_size == 0
    paper.update_market(book(clock, size="0.25"), evidence_key="new", evidence_at=clock())
    assert row.filled_size == D("0.25")
    clock.set(T + timedelta(seconds=2))
    paper.update_market(book(clock, size="100"), evidence_key="new", evidence_at=T + timedelta(seconds=1))
    assert row.filled_size == D("0.25")


@pytest.mark.parametrize("cancel_ms,fill", [(999, False), (1000, False), (1001, True)])
async def test_cancel_race_at_equal_order_activation(cancel_ms, fill):
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(order_latency_ms=1000, cancel_latency_ms=cancel_ms))
    paper.update_market(book(clock, size="10"))
    row = (await paper.submit_orders([order()]))[0]
    await paper.cancel_orders([row.client_order_id])
    assert row in await paper.get_open_orders()
    clock.set(T + timedelta(seconds=1))
    paper.update_market(book(clock, size="10", sequence=2))
    assert bool(paper.fills.all()) == fill
    assert row.status == ("FILLED" if fill else "CANCELLED")
    assert paper.pending_cancellation_deadlines == {}


async def test_repeated_cancel_does_not_extend_deadline_and_replacement_is_reauthorized():
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(cancel_latency_ms=1000))
    paper.update_market(book(clock))
    row = (await paper.submit_orders([order(price="98")]))[0]
    calls = []
    manager = OrderManager(paper, authority=lambda req: calls.append(req))
    desired = [QuoteLevel(side="BID", level_index=0, price=D("97"), size=D("1"), distance_bps=D(1), source_model="CONSTANT_PRODUCT")]
    for ms in (0, 500, 999):
        clock.set(T + timedelta(milliseconds=ms))
        await manager.reconcile("BTC", desired, D(0), D(0))
        assert row in await paper.get_open_orders()
        assert not calls and len(paper.all_orders()) == 1
    clock.set(T + timedelta(seconds=1))
    paper.update_market(book(clock, sequence=2))
    assert row.status == "CANCELLED"
    await manager.reconcile("BTC", desired, D(0), D(0))
    assert len(calls) == 1 and len(await paper.get_open_orders()) == 1
    assert paper.all_orders()[-1].created_at == clock()


async def test_direct_replace_defers_new_exposure_until_cancel_settles():
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(cancel_latency_ms=1000))
    await paper.submit_orders([order(price="98")])
    assert await paper.replace_orders([("order", order("new", price="97"))]) == []
    assert len(await paper.get_open_orders()) == 1


@pytest.mark.parametrize("field", ["initial_equity_quote", "paper_maker_fee_bps", "paper_taker_fee_bps", "max_capital_utilization"])
def test_replay_economics_reject_float_inputs(field):
    dataset = capture()
    payload = request_for(dataset).model_dump(mode="json")
    payload["execution"]["accounting"][field] = 0.5
    with pytest.raises(ValidationError): HistoricalReplayRequest.model_validate(payload)


@pytest.mark.parametrize("market", ["BTC", "ETH", "SOL"])
@pytest.mark.parametrize("control", [dict(), dict(order_latency_ms=1000), dict(cancel_latency_ms=1000),
    dict(slippage_bps="1"), dict(depth_sensitive=True), dict(participation_rate="0"),
    dict(max_fill_fraction="0.5"), dict(allow_partial_fills=False)])
async def test_replay_comparison_reproducible_identical_evidence_and_zero_fill_outputs(vault, market, control):
    dataset = vault.save(capture(market=market))
    args = args_for(vault, dataset, **control)
    service = SimulationService()
    result = await service.replay_history(**args)
    assert result == await service.replay_history(**args)
    assert HistoricalReplayResult.model_validate_json(result.model_dump_json()) == result
    baseline = await service.replay_history(**inputs(vault, dataset))
    assert result.provenance == baseline.provenance
    assert result.execution_assumptions_fingerprint == args["request"].execution.paper.fingerprint
    assert result.modeling_fingerprint != baseline.modeling_fingerprint
    for segment, base_segment in zip(result.segments, baseline.segments):
        assert segment.frames == base_segment.frames
        assert segment.dataset_fingerprint == base_segment.dataset_fingerprint
        assert segment.baseline_result_json == base_segment.simulation_result_json
        assert segment.fill_count == 0  # Absence of external reference evidence may suppress all risk authorization.
        assert segment.fill_count_delta == 0 and segment.session_pnl_delta == 0
        archive = json.loads(segment.simulation_result_json)
        assert archive["execution_assumptions_fingerprint"] == result.execution_assumptions_fingerprint
        assert archive["vault"]["execution_accounting"]["execution_accounting_consistent"]
        tampered = segment.model_dump(mode="json")
        tampered["baseline_result_json"] = "{}"
        with pytest.raises(ValidationError): type(segment).model_validate(tampered)


@pytest.mark.parametrize("market", ["BTC", "ETH", "SOL"])
async def test_segment_resets_match_independent_model_runs(vault, market):
    dataset = vault.save(capture(market=market, times=(0, 1, 4, 5), gaps=((1, 4, "DISCONNECT"),)))
    args = args_for(vault, dataset, order_latency_ms=60000, cancel_latency_ms=60000, depth_sensitive=True)
    result = await SimulationService().replay_history(**args)
    assert len(result.segments) == 2 and not hasattr(result, "return_pct")
    for segment in result.segments:
        window = args["request"].model_copy(update={"start_at": segment.frames[0].evaluated_at,
                                                  "end_at": segment.frames[-1].evaluated_at})
        isolated = await SimulationService().replay_history(**{**args, "request": window})
        assert isolated.segments[0].simulation_result_json == segment.simulation_result_json
        assert isolated.segments[0].baseline_result_json == segment.baseline_result_json


@pytest.mark.parametrize("missing", ["mark_price", "oracle_price", "funding_rate", "open_interest_base"])
async def test_modeled_replay_never_substitutes_absent_economics(vault, missing):
    context = dict(mark_price="60000", oracle_price="60000", funding_rate="0", open_interest_base="10")
    del context[missing]
    dataset = vault.save(capture(partial={i: context for i in range(4)}))
    with pytest.raises(ReplayRejected):
        await SimulationService().replay_history(**args_for(vault, dataset))


async def test_modeled_replay_receipt_ties_and_unknown_source_time(vault):
    payload = capture(reverse_ties=True).model_dump(mode="json")
    payload["dataset_fingerprint"] = None
    for point in payload["observations"]:
        if point["kind"] == "L2":
            point["source_timestamp"] = None
            point["source_event_time_verified"] = False
    dataset = vault.save(validate_bytes(json.dumps(payload).encode()))
    result = await SimulationService().replay_history(**args_for(vault, dataset, order_latency_ms=1))
    assert [f.evaluated_at for f in result.segments[0].frames] == [T+timedelta(seconds=i) for i in range(4)]
    assert all(f.book_observation.source_timestamp is None for f in result.segments[0].frames)


@pytest.mark.parametrize("market", ["BTC", "ETH", "SOL"])
@pytest.mark.parametrize("controls", [dict(), dict(order_latency_ms=1000), dict(cancel_latency_ms=1000),
    dict(depth_sensitive=True, participation_rate="0.1", max_fill_fraction="0.5")])
async def test_engine_trade_fee_funding_risk_and_exposure_reconciliation(market, controls):
    from app.simulation.market_profiles import profile, ResearchPerpMarketMetadata, DEMO_PROFILES
    selected = profile(ResearchPerpMarketMetadata(market=market, sz_decimals=DEMO_PROFILES[market][1],
        metadata_status="DEMO_PROFILE", metadata_source="SYNTHETIC_TEST"))
    kwargs = dict(scenario="FLASH_MOVE", frames=12, strategy=StrategyConfig(), agents=AgentConfig(),
        risk=RiskFirewallConfig(), market_profile=selected,
        simulation=SimulationConfig(max_frames=12, execution=assumptions(**controls),
            accounting=AccountingConfig(paper_fee_model_enabled=True, paper_funding_accounting_enabled=True,
                                        paper_funding_interval_seconds=1)))
    result = await SimulationService().run_scenario(**kwargs)
    assert result == await SimulationService().run_scenario(**kwargs)
    assert result.vault.execution_accounting.execution_accounting_consistent
    assert result.metrics.ending_inventory_base == sum((D(f["size"]) * (1 if f["side"] == "BID" else -1)
                                                       for f in result.fills), D(0))
    assert result.metrics.filled_notional == sum((D(f["size"]) * D(f["price"]) for f in result.fills), D(0))
    assert result.vault.fees_quote == result.metrics.filled_notional * D("0.0003")
    assert result.vault.net_pnl_quote == result.vault.gross_pnl_quote - result.vault.fees_quote + result.vault.funding_quote
    assert result.vault.equity_quote == result.vault.initial_equity_quote + result.vault.net_pnl_quote
    funding = [e for e in result.accounting_ledger if e.event_type == "FUNDING"]
    assert sum((e.funding_delta_quote for e in funding), D(0)) == result.vault.funding_quote
    if market in {"BTC", "ETH"} and not controls.get("cancel_latency_ms"):
        assert result.metrics.fill_count > 0 and result.vault.funding_quote != 0
    # SOL's default strategy scaling may be suppressed by existing risk limits;
    # zero fills remain a valid outcome and do not justify relaxing production risk.
    assert sum(result.metrics.risk_state_counts.values()) == 12
    assert all(D(o["filled_size"]) <= D(o["size"]) for o in result.orders)


@pytest.mark.parametrize("side", ["BID", "ASK"])
async def test_sampled_funding_and_close_reconcile_modeled_partial_trades(side):
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(depth_sensitive=True))
    acct = AccountingService("BTC", clock=clock, config=AccountingConfig(paper_fee_model_enabled=True,
        paper_funding_accounting_enabled=True, paper_funding_interval_seconds=1))
    paper.on_fill = acct.ingest_fill
    paper.update_market(book(clock))
    row = (await paper.submit_orders([order(side=side, price="110" if side == "BID" else "90")]))[0]
    assert row.filled_size == D("0.6")
    clock.set(T + timedelta(seconds=1))
    assert acct.accrue_funding(effective_at=clock(), mark=D("100"), rate=D("0.001"), evidence_version=1)
    expected = D("-0.06") if side == "BID" else D("0.06")
    assert acct.snapshot().funding_quote == expected
    assert not acct.accrue_funding(effective_at=clock(), mark=D("100"), rate=D("0.001"), evidence_version=1)
    await paper.cancel_all()  # Cancel the unfilled remainder before reversing.
    paper.update_market(book(clock, size="1", sequence=2))
    await paper.submit_orders([order("close", side="ASK" if side == "BID" else "BID",
        price="90" if side == "BID" else "110", size="0.6")])
    acct.observe_execution_fills(paper.fills.all())
    acct.mark(D(100), observed_at=clock())
    state = acct.snapshot()
    assert state.position_base == 0 and state.unrealized_pnl_quote == 0
    assert state.funding_quote == expected
    assert state.execution_accounting.execution_accounting_consistent
    assert state.equity_quote == state.initial_equity_quote + state.realized_pnl_quote - state.fees_quote + expected


@pytest.mark.parametrize("held_call", [1, 2])
async def test_modeled_comparison_owns_single_slot_through_cancel_and_shutdown(vault, monkeypatch, held_call):
    from app.main import app
    from app.config import Settings
    from app.runtime import HyperAmmRuntime
    dataset = vault.save(capture())
    worker = SimulationExecutor()
    monkeypatch.setattr(app.state, "runtime", HyperAmmRuntime(Settings(_env_file=None)), raising=False)
    monkeypatch.setattr(app.state, "simulation_executor", worker, raising=False)
    monkeypatch.setattr(app.state, "historical_replay_root", vault.root, raising=False)
    loop, started, release, calls = asyncio.get_running_loop(), asyncio.Event(), Event(), []
    original = SimulationEngine.run
    async def held(self, **kwargs):
        calls.append(kwargs["simulation_config"].execution.mode)
        if len(calls) == held_call:
            loop.call_soon_threadsafe(started.set)
            assert release.wait(10)
        return await original(self, **kwargs)
    monkeypatch.setattr(SimulationEngine, "run", held)
    body = args_for(vault, dataset, cancel_latency_ms=1000)["request"].model_dump(mode="json")
    shutdown = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        task = asyncio.create_task(client.post("/api/v1/historical-replay/run", json=body))
        try:
            await asyncio.wait_for(started.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            assert (await client.post("/api/v1/historical-replay/run", json=body)).status_code == 429
            assert (await client.post("/api/v1/simulation/run", json={"frames": 3})).status_code == 429
            with pytest.raises(ResearchBusyError): await worker.execute("historical_catalog", storage_root=vault.root)
            shutdown = asyncio.create_task(worker.shutdown())
            await asyncio.sleep(0)
            assert not shutdown.done() and worker._busy
        finally:
            release.set()
            await (shutdown or worker.shutdown())
    assert calls == ["BASELINE", "MODELED_CROSSING"]
    assert not worker._busy and all(not thread.is_alive() for thread in worker._pool._threads)


@pytest.mark.parametrize("kill", [False, True])
async def test_modeled_replay_preserves_seeded_runtime_signer_risk_and_kill_switch(vault, kill):
    from app.config import Settings
    from app.runtime import HyperAmmRuntime
    from app.market_data.mock import MockMarketDataAdapter
    from test_phase14_research_vault import authority
    rt = HyperAmmRuntime(Settings(_env_file=None))
    snapshot = MockMarketDataAdapter().snapshot_for(4)
    await rt.market._accept(snapshot)
    await rt.refresh_once()
    await rt.paper.submit_orders([order("seed", market="ETH", price=str(snapshot.best_ask), size="0.1")])
    await rt.refresh_once()
    rt.strategy.running = True
    await rt._execution_authority()
    async with rt.execution_lock:
        await rt.orders.reconcile_locked(rt.config.market, rt.quotes, rt.config.replace_tolerance_bps, rt.config.size_tolerance)
    rt.accounting_service.reserve(rt.quotes, await rt.execution.get_open_orders())
    if kill:
        await rt.activate_kill()
        await rt.refresh_once()
    before = deepcopy(authority(rt))
    services = tuple(id(x) for x in (rt.market, rt.perp_context_service, rt.reference_service, rt.testnet))
    signer = (id(rt.testnet._exchange), stable_fingerprint(dict(enabled=rt.testnet.enabled,
        private_key=rt.testnet.private_key, account_address=rt.testnet.account_address)))
    executor = SimulationExecutor()
    try:
        for market in ("BTC", "ETH", "SOL"):
            dataset = vault.save(capture(market=market))
            args = args_for(vault, dataset, order_latency_ms=1000, cancel_latency_ms=1000, depth_sensitive=True)
            args.update(strategy=rt.config.model_copy(deep=True), agents=rt.agent_config.model_copy(deep=True),
                        risk=rt.risk_config.model_copy(deep=True))
            assert (await executor.execute("replay_history", **args)).frame_count == 4
            args["request"] = args["request"].model_copy(update={"dataset_fingerprint": "0"*64})
            with pytest.raises(ReplayRejected): await executor.execute("replay_history", **args)
    finally:
        await executor.shutdown()
    assert authority(rt) == before
    assert services == tuple(id(x) for x in (rt.market, rt.perp_context_service, rt.reference_service, rt.testnet))
    assert signer == (id(rt.testnet._exchange), stable_fingerprint(dict(enabled=rt.testnet.enabled,
        private_key=rt.testnet.private_key, account_address=rt.testnet.account_address)))


async def test_replay_asof_pairing_carries_original_book_identity_and_time(vault, monkeypatch):
    dataset = vault.save(capture(context_offset_ms=20))
    args = args_for(vault, dataset, order_latency_ms=1)
    args["request"] = args["request"].model_copy(update={"policy": args["request"].policy.model_copy(update={"max_component_age_ms": 1000})})
    observed = []
    original = PaperExecutionAdapter.update_market
    def update(self, snapshot, **kwargs):
        if self.assumptions.modeled:
            observed.append((kwargs["evidence_key"], kwargs["evidence_at"]))
        return original(self, snapshot, **kwargs)
    monkeypatch.setattr(PaperExecutionAdapter, "update_market", update)
    result = await SimulationService().replay_history(**args)
    assert observed == [(stable_fingerprint(f.book_observation), f.book_observation.received_at)
                        for f in result.segments[0].frames]
    assert any(f.book_observation.received_at < f.evaluated_at for f in result.segments[0].frames)


async def test_pending_cancellation_remains_reserved_and_is_visible():
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions(cancel_latency_ms=1000))
    acct = AccountingService("BTC", clock=clock)
    paper.update_market(book(clock))
    row = (await paper.submit_orders([order(price="98")]))[0]
    acct.mark(D(100), observed_at=clock())
    acct.reserve([], await paper.get_open_orders())
    reserved = acct.snapshot().reserved_capital_quote
    await paper.cancel_all()
    acct.reserve([], await paper.get_open_orders())
    assert acct.snapshot().reserved_capital_quote == reserved > 0
    assert paper.pending_cancellation_deadlines == {row.client_order_id: T+timedelta(seconds=1)}
    clock.set(T + timedelta(seconds=1))
    paper.update_market(book(clock, sequence=2))
    acct.reserve([], await paper.get_open_orders())
    assert acct.snapshot().reserved_capital_quote == 0
    assert paper.pending_cancellation_deadlines == {}


@pytest.mark.parametrize("fees", [False, True])
@pytest.mark.parametrize("funding", [False, True])
async def test_fee_and_funding_toggles_reuse_existing_accounting(fees, funding):
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions())
    acct = AccountingService("BTC", clock=clock, config=AccountingConfig(paper_fee_model_enabled=fees,
        paper_funding_accounting_enabled=funding, paper_funding_interval_seconds=1))
    paper.on_fill = acct.ingest_fill
    paper.update_market(book(clock, size="1"))
    await paper.submit_orders([order()])
    clock.set(T + timedelta(seconds=1))
    acct.accrue_funding(effective_at=clock(), mark=D(100), rate=D("0.001"), evidence_version=1)
    acct.mark(D(100), observed_at=clock())
    assert acct.snapshot().fees_quote == (D("0.0303") if fees else D(0))
    assert acct.snapshot().funding_quote == (D("-0.1") if funding else D(0))


async def test_default_baseline_matches_explicit_baseline_outputs():
    service = SimulationService()
    args = dict(scenario="FLASH_MOVE", frames=12, strategy=StrategyConfig(), agents=AgentConfig(), risk=RiskFirewallConfig())
    default = await service.run_scenario(**args, simulation=SimulationConfig(max_frames=12))
    explicit = await service.run_scenario(**args, simulation=SimulationConfig(max_frames=12,
        execution=PaperExecutionAssumptions()))
    assert default == explicit
    assert default.metrics.fill_count > 0
    assert default.pending_cancellation_deadlines is None
    assert all(f["source"] == "SIMULATED PAPER FILL" for f in default.fills)


async def test_accounting_conflicting_modeled_fill_identity_still_fails_closed():
    clock = SimulationClock(T)
    paper = PaperExecutionAdapter(clock, assumptions=assumptions())
    acct = AccountingService("BTC", clock=clock)
    paper.on_fill = acct.ingest_fill
    paper.update_market(book(clock, size="1"))
    await paper.submit_orders([order()])
    fill = paper.fills.all()[0]
    assert not acct.ingest_fill(fill)  # Idempotent retry of the same immutable economics.
    with pytest.raises(ValueError, match="conflicting fill replay economics"):
        acct.ingest_fill(fill.model_copy(update={"price": fill.price+D(1)}))
    assert acct.error


@pytest.mark.parametrize("value", ["0", "1", "10", "100", "1000", "0.000000000000000001"])
def test_decimal_serialization_stays_plain_for_strict_roundtrip(value):
    a = assumptions(slippage_bps=value)
    assert json.loads(a.model_dump_json())["slippage_bps"] == value
    assert PaperExecutionAssumptions.model_validate_json(a.model_dump_json()) == a
    assert PaperExecutionAdapter(assumptions=a).assumptions.fingerprint == a.fingerprint


def test_saved_phase162_receipt_retains_original_shape_and_fingerprints():
    from pathlib import Path
    # Generated by untouched main d5ca0db using the existing two-frame capture
    # fixture, with trace disabled. This is a synthetic test of stored contracts.
    original = (Path(__file__).parent / "fixtures" / "phase162-receipt.json").read_text().strip()
    receipt = HistoricalReplayResult.model_validate_json(original)
    assert receipt.result_fingerprint == "bf3632854bc696a3c69fe21fd8f7327105fcdb61e565e0c5fd51e09e2050b6bc"
    assert receipt.model_dump_json() == original
    assert receipt.request.execution.paper == PaperExecutionAssumptions()
    assert receipt.execution_assumptions_fingerprint is None


@pytest.mark.parametrize("value", [D("1e1000000"), D("1e-1000000"), D("1e31")])
def test_internal_decimal_extremes_reject_without_context_overflow(value):
    with pytest.raises(ValidationError): assumptions(slippage_bps=value)


def test_signed_zero_has_the_same_assumption_identity():
    assert assumptions(slippage_bps=D("-0")).fingerprint == assumptions(slippage_bps=D(0)).fingerprint
