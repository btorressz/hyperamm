"""Independent generalized PAPER provenance, economics and admission regressions."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from threading import Event

import pytest
from eth_account import Account
from hyperliquid.exchange import Exchange
from pydantic import ValidationError

from app import main
from app.accounting.service import AccountingService
from app.agents.evidence import AgentTelemetryStore
from app.agents.supervisor import AgentSupervisor
from app.amm.models import QuoteLevel
from app.config import Settings
from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
from app.execution.models import Fill, StrategyOrder
from app.infrastructure.research import CoordinatedSimulationExecutor
from app.market_data.history import MarketPriceHistory
from app.market_data.models import MarketDataMode
from app.portfolio_research.models import MarketResearchAllocation, PortfolioCapitalBudget
from app.references.consensus import ReferenceConsensusPolicy
from app.references.models import GENERALIZED_REFERENCE_SOURCE, SYNTHETIC_AGREEMENT, PriceEvidence, ProviderId
from app.references.service import ReferenceService
from app.risk.authorization import authorize, fingerprint
from app.risk.firewall import PnlDrawdown, RiskFirewall
from app.simulation import generalized_market_profiles as paper, version
from app.simulation.engine import SimulationEngine
from app.simulation.models import SimulationDataset
from app.simulation.references import build_simulated_references
from app.simulation.scenarios import generate_scenario
from app.strategy.inventory import build_inventory_state
from app.strategy.quote_engine import QuoteEngine
from app.terminal.models import TerminalSnapshot
from test_phase182_generalized_paper import URL, admit, api_client, evidence, proposal_for
from test_redis_infrastructure import infrastructure


@pytest.fixture(autouse=True)
def venue_isolation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("generalized PAPER reached a venue operation or signer")
    for target, methods in (
        (Account, ("from_key",)),
        (Exchange, ("__init__", "order", "bulk_orders", "cancel", "bulk_cancel", "bulk_modify_orders_new")),
        (HyperliquidTestnetExecutionAdapter, ("__init__", "submit_orders", "replace_orders", "cancel_orders")),
    ):
        for method in methods:
            monkeypatch.setattr(target, method, forbidden)


def test_synthetic_reference_identity_times_consensus_and_operational_fences(monkeypatch):
    admission, prepared = admit(evidence())
    dataset = SimulationDataset.model_validate_json(prepared.dataset.model_dump_json())
    frame = dataset.frames[0]
    assert frame.reference_prices.provenance == GENERALIZED_REFERENCE_SOURCE
    assert frame.market.simulated and frame.perp_context.simulated
    assert frame.perp_context.source == "GENERALIZED_PAPER"
    kwargs = dict(agreement_bps=Decimal(30), outlier_bps=Decimal(75), version=1)
    refs = build_simulated_references(frame, **kwargs)
    assert refs.consensus.confidence_state == SYNTHETIC_AGREEMENT
    assert refs.consensus.consensus_price > 0 and refs.consensus.exchange_reference_price is None
    assert refs.consensus.native_oracle_price is None and refs.consensus.primary_oracle_price is None
    assert all(item.simulated and item.source_id == GENERALIZED_REFERENCE_SOURCE
               and item.source_timestamp is None and item.observed_at == frame.timestamp
               and item.age_ms == 0 and item.healthy for item in refs.evidence.values())
    provider_shaped = {
        provider.value: item.model_copy(update={"provider": provider})
        for provider, item in zip((ProviderId.REDSTONE, ProviderId.HYPERLIQUID_ORACLE, ProviderId.KRAKEN),
                                  refs.evidence.values())
    }
    for item in provider_shaped.values():
        with pytest.raises(ValidationError):
            PriceEvidence.model_validate(item.model_dump())

    policy = ReferenceConsensusPolicy()
    for rows in (refs.evidence, provider_shaped):
        rejected = policy.evaluate(frame.market.market, rows, **kwargs)
        assert rejected.confidence_state == "INSUFFICIENT" and rejected.consensus_price is None
    with pytest.raises(ValueError, match="firewall context"):
        RiskFirewall(prepared.risk).evaluate(refs=refs, quotes=[], current_position=Decimal(0),
            mark=frame.perp_context.mark_price, liquidation=None, pnl=None, market_version=1,
            inventory_version=0, perp_version=1)
    with pytest.raises(ValueError, match="authorization context"):
        authorize([], refs, None)

    service = ReferenceService(Settings(_env_file=None), market=frame.market.market, mode=MarketDataMode.DEMO)
    with pytest.raises(ValueError, match="context cannot enter the reference service"):
        service.snapshot(frame.market, frame.perp_context, agreement_bps=Decimal(30), outlier_bps=Decimal(75))
    monkeypatch.setattr(service, "_demo_external", lambda *_: provider_shaped)
    with pytest.raises(ValueError, match="cannot enter the reference service"):
        service.snapshot(frame.market, frame.perp_context.model_copy(update={"source": "DEMO"}),
                         agreement_bps=Decimal(30), outlier_bps=Decimal(75))
    assert service._version == 0 and service._fingerprint is None

    terminal = json.loads((Path(__file__).resolve().parents[2] / "frontend/tests/fixtures/terminal-valid.json").read_text())
    for key, value in (("references", refs), ("reference_consensus", refs.consensus)):
        with pytest.raises(ValidationError, match="cannot enter terminal evidence"):
            TerminalSnapshot.model_validate({**terminal, key: value})

    fill = Fill(client_order_id="paper-fill", market=frame.market.market, side="BID",
                size=Decimal(1), price=frame.market.mid_price, timestamp=frame.timestamp)
    telemetry = AgentTelemetryStore()
    assert telemetry.observe_fill_from_references(fill, refs)
    retained, = telemetry._fills
    assert retained.reference_source == GENERALIZED_REFERENCE_SOURCE
    assert retained.reference_timestamp == frame.timestamp and all(
        item.source_timestamp is None for item in retained.reference_provenance.values())
    with pytest.raises(ValueError, match="simulated fill"):
        telemetry.observe_fill_from_references(
            fill.model_copy(update={"execution_mode": "TESTNET", "source": "TESTNET"}), refs)

    native = build_simulated_references(generate_scenario("QUIET", frames=2).frames[0], **kwargs)
    assert native.consensus.confidence_state == "VERIFIED"
    assert native.evidence["REDSTONE"].source_timestamp == frame.timestamp
    assert fingerprint(native) != fingerprint(refs)
    assert admission.profile.evidence_boundary.risk_readiness == "SINGLE_MARKET_RESEARCH_ONLY"


async def run_paper(record, proposal):
    admission, prepared = admit(record, proposal)
    assert prepared is not None, admission.reason
    output = await paper.execute_paper(SimulationEngine(), proposal=proposal, metadata=record,
        network=record.identity.network, max_age_seconds=60, expected=admission.binding)
    return paper.GeneralizedPaperResult.model_validate_json(output.model_dump_json()), prepared


def assert_conservation(result):
    vault = result.vault
    assert vault.net_pnl_quote == vault.realized_pnl_quote + vault.unrealized_pnl_quote - vault.fees_quote + vault.funding_quote
    assert vault.equity_quote == vault.initial_equity_quote + vault.net_pnl_quote
    assert result.metrics.starting_equity == vault.initial_equity_quote
    assert result.metrics.ending_equity == vault.equity_quote
    assert result.metrics.realized_pnl == vault.realized_pnl_quote
    assert result.metrics.unrealized_pnl == vault.unrealized_pnl_quote
    chronological = result.accounting_ledger[::-1]
    assert sum(entry.position_delta_base for entry in chronological) == vault.position_base
    assert sum(entry.realized_pnl_delta for entry in chronological) == vault.realized_pnl_quote
    assert sum(entry.fee_delta_quote for entry in chronological) == vault.fees_quote
    assert sum(entry.funding_delta_quote for entry in chronological) == vault.funding_quote
    assert all(entry.simulated for entry in result.accounting_ledger)


@pytest.mark.parametrize(("dex", "name", "precision", "price"), [
    ("", "DOGE", 0, "0.1234"),
    ("crypto", "ALT", 1, "0.0123"),
    ("metals", "GOLD", 3, "2500"),
    ("energy", "OIL", 4, "90"),
    ("equity", "INDEX", 5, "1000"),
])
async def test_representative_fixtures_and_maximum_modeled_fees(dex, name, precision, price):
    record = evidence(dex=dex, name=name, precision=precision)
    proposal = proposal_for(record, price=price, scenario="FLASH_MOVE", frames=40,
        economics={"model": "HYPOTHETICAL_LINEAR", "maker_fee_bps": "100",
                   "taker_fee_bps": "100", "funding_interval_seconds": 3})
    output, prepared = await run_paper(record, proposal)
    repeated, _ = await run_paper(record, proposal)
    assert output.result_fingerprint == repeated.result_fingerprint
    result = output.result
    assert any(point.reference_confidence == SYNTHETIC_AGREEMENT for point in result.trace)
    assert all(point.reference_confidence != "VERIFIED" for point in result.trace)
    assert len(result.fills) >= 2
    assert_conservation(result)
    fee_events = [entry for entry in result.accounting_ledger if entry.event_type == "FEE"]
    assert len(fee_events) == len(result.fills)
    assert all(entry.source == "PAPER_CONFIG" for entry in fee_events)
    assert result.vault.fees_quote == sum(Decimal(fill["size"]) * Decimal(fill["price"]) / 100 for fill in result.fills)
    active = [StrategyOrder.model_validate(order) for order in result.orders
              if order["status"] in {"OPEN", "PARTIALLY_FILLED"}]
    mark = prepared.dataset.frames[-1].perp_context.mark_price
    assert result.vault.reserved_capital_quote >= abs(result.vault.position_base) * mark + sum(
        order.price * (order.size - order.filled_size) for order in active)
    assert result.vault.reserved_capital_quote > 0
    assert output.admission.profile.evidence_boundary.capital_reservation == "SIMULATED_FULL_NOTIONAL"


@pytest.mark.parametrize(("scenario", "interval"), [("QUIET", 3), ("POSITIVE_FUNDING_STRESS", 4),
    ("NEGATIVE_FUNDING_STRESS", 5), ("HIGH_VOLATILITY", 3)])
async def test_zero_fees_funding_boundaries_and_inventory(scenario, interval):
    record = evidence()
    output, prepared = await run_paper(record, proposal_for(record, scenario=scenario, frames=40,
        economics={"model": "HYPOTHETICAL_LINEAR", "funding_interval_seconds": interval}))
    result = output.result
    assert_conservation(result)
    entries = sorted((entry for entry in result.accounting_ledger if entry.event_type == "FUNDING"),
                     key=lambda entry: entry.timestamp)
    assert result.vault.fees_quote == 0 and entries
    first, *remaining = prepared.dataset.frames
    boundaries = [frame for frame in remaining if int(frame.timestamp.timestamp()) % interval == 0]
    assert [entry.timestamp for entry in entries] == [frame.timestamp for frame in boundaries]
    for entry, frame in zip(entries, boundaries, strict=True):
        assert entry.source == "PAPER_RESEARCH_INTERVAL"
        assert entry.funding_delta_quote == -entry.position_base * frame.perp_context.mark_price * frame.perp_context.funding_rate
    assert first.timestamp < entries[0].timestamp
    if scenario == "HIGH_VOLATILITY":
        assert {fill["side"] for fill in result.fills} == {"BID", "ASK"}
        assert len({fill["timestamp"] for fill in result.fills}) > 1
        assert max(point.inventory_base for point in result.trace) > 0 > min(point.inventory_base for point in result.trace)
    else:
        assert not result.fills and result.vault.position_base == result.vault.funding_quote == 0


@pytest.mark.parametrize("side", ["BID", "ASK"])
def test_accounting_distinguishes_maker_taker_and_funding_sign(side):
    record = evidence()
    _, prepared = admit(record, proposal_for(record, economics={
        "model": "HYPOTHETICAL_LINEAR", "maker_fee_bps": "7", "taker_fee_bps": "100",
        "funding_interval_seconds": 1}))
    frame = prepared.dataset.frames[0]
    service = AccountingService(record.identity.stable_key, config=prepared.simulation.accounting, clock=lambda: frame.timestamp)
    for role in ("MAKER", "TAKER"):
        service.ingest_fill(Fill(client_order_id=role, market=service.market, size=Decimal(10),
            price=Decimal(10), timestamp=frame.timestamp, side=side, liquidity=role))
    for offset, rate in ((1, Decimal(".00045")), (2, Decimal("-.00045"))):
        service.accrue_funding(effective_at=frame.timestamp + timedelta(seconds=offset),
                               mark=Decimal(10), rate=rate)
    fees = [entry.fee_delta_quote for entry in service.ledger.entries() if entry.event_type == "FEE"]
    funding = [entry.funding_delta_quote for entry in service.ledger.entries() if entry.event_type == "FUNDING"]
    assert fees == [Decimal("1"), Decimal(".07")]
    assert funding == ([Decimal(".09"), Decimal("-.09")] if side == "BID" else [Decimal("-.09"), Decimal(".09")])


async def test_quote_retirement_and_recovery_use_current_synthetic_evidence(monkeypatch):
    admission, prepared = admit(evidence())
    frames = list(prepared.dataset.frames)
    index = 3
    frame = frames[index]
    frames[index] = frame.model_copy(update={"reference_prices": frame.reference_prices.model_copy(
        update={"redstone": None, "kraken": None})})
    dataset = SimulationDataset(market=prepared.dataset.market, source=prepared.dataset.source, frames=tuple(frames))
    agent_inputs = []
    evaluate = AgentSupervisor.evaluate

    def capture_agent(self, *, evidence, **kwargs):
        agent_inputs.append(evidence)
        return evaluate(self, evidence=evidence, **kwargs)

    monkeypatch.setattr(AgentSupervisor, "evaluate", capture_agent)
    result = await SimulationEngine().run(dataset=dataset, strategy_config=prepared.strategy,
        agent_config=prepared.agents, risk_config=prepared.risk, simulation_config=prepared.simulation,
        generalized_profile=admission.profile)
    assert result.trace[index - 1].open_order_count > 0
    halt = result.trace[index]
    assert (halt.reference_confidence, halt.risk_state, halt.authorized_quote_count, halt.open_order_count) == (
        "INSUFFICIENT", "HALT", 0, 0)
    assert result.trace[-1].risk_state == "NORMAL" and result.trace[-1].open_order_count > 0
    assert agent_inputs[0].reference_confidence == SYNTHETIC_AGREEMENT
    assert agent_inputs[index].reference_confidence == "INSUFFICIENT"
    assert all(item.simulated and all(row.is_generalized_paper for row in item.reference_provenance.values())
               for item in agent_inputs)
    assert any(order["status"] == "CANCELLED" for order in result.orders)
    assert not result.fills
    for order in (order for order in result.orders if order["status"] == "OPEN"):
        price = Decimal(order["price"])
        book = frames[-1].market
        assert price > 0 and Decimal(order["size"]) > 0
        assert price < book.best_ask if order["side"] == "BID" else price > book.best_bid

    quote = QuoteLevel(side="BID", price=Decimal(".12341"), size=Decimal(1),
        level_index=0, distance_bps=Decimal(1), source_model="CONSTANT_PRODUCT")
    duplicate = quote.model_copy(update={"price": Decimal(".12342"), "level_index": 1})
    profile = admission.profile
    assert len(profile.normalize_quotes([quote, duplicate], Decimal(".124"))) == 1
    with pytest.raises(ValueError, match="PRICE_UNREPRESENTABLE"):
        profile.normalize_quotes([quote, duplicate], Decimal(".124"), preflight=True)

    strategy = prepared.strategy
    hard_limit = strategy.hard_inventory_limit_base
    lot = Decimal(1).scaleb(-profile.sz_decimals)
    history = MarketPriceHistory()
    history.add_snapshot(frame.market)
    refs = build_simulated_references(frame, agreement_bps=Decimal(30), outlier_bps=Decimal(75), version=frame.sequence)
    for sign, increasing, reducing in ((1, "BID", "ASK"), (-1, "ASK", "BID")):
        for quantity in (hard_limit - lot, hard_limit):
            position = sign * quantity
            inventory = build_inventory_state(market=profile.market, position=position,
                target=Decimal(0), soft_limit=strategy.soft_inventory_limit_base, source="PAPER",
                updated_at=frame.timestamp, version=1)
            _, _, proposed, inventory_decision, _, _ = QuoteEngine().generate_perp_market_adaptive(
                strategy, frame.market, inventory, history, frame.perp_context)
            normalized = profile.normalize_quotes(proposed, inventory_decision.reservation_price)
            sides = {level.side for level in normalized}
            if quantity == hard_limit:
                assert sides == {reducing}
            else:
                assert increasing in sides
                risk = RiskFirewall(prepared.risk, generalized_paper=True).evaluate(
                    refs=refs, quotes=normalized, current_position=position, mark=frame.perp_context.mark_price,
                    liquidation=None, pnl=PnlDrawdown(source="PAPER_RESEARCH", simulated=True),
                    market_version=1, inventory_version=1, perp_version=1)
                assert risk.state == "HALT" and not risk.allow_quotes
                assert "projected base exposure exceeds limit" in risk.reasons


async def test_scope_cannot_substitute_for_portfolio_or_exchange_evidence(api_client):
    client, _, _, _ = api_client
    proposal = proposal_for(evidence()).model_dump(mode="json")
    preview = (await client.post(f"{URL}/eligibility", json=proposal)).json()
    response = await client.post(f"{URL}/run", json={**proposal, "expected": preview["binding"]})
    assert response.status_code == 200
    run = response.json()
    with pytest.raises(ValidationError):
        MarketResearchAllocation(market=run["result"]["research_market"], allocated_equity_quote="1")
    with pytest.raises(ValidationError):
        PortfolioCapitalBudget(quote_currency=preview["profile"]["evidence_boundary"]["accounting_units"],
                               total_equity_quote="1")
    with pytest.raises(ValidationError):
        paper.GeneralizedPaperResult.model_validate_json(
            response.content.replace(b'"execution_eligible":false', b'"execution_eligible":true', 1))
    with pytest.raises(ValidationError):
        paper.GeneralizedPaperResult.model_validate_json(
            response.content.replace(b'"SINGLE_MARKET_RESEARCH_ONLY"', b'"RISK_READY"', 1))
    for fields in ({"collateral_mode": "CROSS"}, {"risk": {"enabled": False}}, {"eligible": True},
                   {"execution_mode": "TESTNET"}, {"execution_mode": "LIVE"},
                   {"admission": preview}, {"risk_ready": True}):
        denied = await client.post(f"{URL}/run", json={**proposal, "expected": preview["binding"], **fields})
        assert denied.status_code == 422 and denied.json()["reason"] == "CONFIGURATION_INVALID"


async def test_catalog_only_replacement_retires_delayed_worker_and_old_binding(api_client, monkeypatch):
    client, discovery, executor, _ = api_client
    proposal = proposal_for(evidence()).model_dump(mode="json")
    concurrent = await asyncio.gather(*(client.post(f"{URL}/eligibility", json=proposal) for _ in range(4)))
    assert all(response.status_code == 200 for response in concurrent)
    binding = concurrent[0].json()["binding"]
    assert all(response.json()["binding"] == binding for response in concurrent)

    waiting, release = asyncio.Event(), asyncio.Event()
    execute = executor.execute

    async def delayed(*args, **kwargs):
        waiting.set()
        await release.wait()
        return await execute(*args, **kwargs)

    async def forbidden(*args, **kwargs):
        pytest.fail("superseded generation started engine")
    monkeypatch.setattr(executor, "execute", delayed)
    monkeypatch.setattr(SimulationEngine, "run", forbidden)
    request = asyncio.create_task(client.post(f"{URL}/run", json={**proposal, "expected": binding}))
    try:
        await asyncio.wait_for(waiting.wait(), 3)
        old_provider = discovery._client

        def refreshed(method, dex, deadline):
            data = old_provider(method, dex, deadline)
            if dex == "xyz" and method == "meta":
                data["universe"].append({"name": "xyz:OTHER", "szDecimals": 2})
            return data

        discovery._client = refreshed
        discovery._expires = 0
        refreshed = (await client.post(f"{URL}/eligibility", json=proposal)).json()["binding"]
        assert refreshed["metadata_fingerprint"] == binding["metadata_fingerprint"]
        assert refreshed["catalog_fingerprint"] != binding["catalog_fingerprint"]
    finally:
        release.set()
    stale = await request
    assert stale.status_code == 503 and stale.json()["reason"] == "METADATA_STALE"
    rejected = await client.post(f"{URL}/run", json={**proposal, "expected": binding})
    assert rejected.status_code == 409 and rejected.json()["reason"] == "CATALOG_FINGERPRINT_MISMATCH"


@pytest.mark.parametrize(("catalog_change", "http", "reason"), [
    ("delisted", 422, "MARKET_DELISTED"),
    ("precision", 409, "METADATA_FINGERPRINT_MISMATCH"),
    ("partial", 503, "METADATA_STALE"),
    ("missing", 503, "METADATA_UNAVAILABLE"),
    ("schema_version", 503, "METADATA_UNAVAILABLE"),
    ("catalog_version", 503, "METADATA_UNAVAILABLE"),
])
async def test_refresh_and_catalog_failures_are_scoped(api_client, monkeypatch, catalog_change, http, reason):
    client, discovery, executor, _ = api_client
    proposal = proposal_for(evidence()).model_dump(mode="json")
    preview = await client.post(f"{URL}/eligibility", json=proposal)
    binding = preview.json()["binding"]
    original_catalog = discovery.catalog
    original_client = discovery._client

    async def changed_catalog():
        catalog = await original_catalog()
        if catalog_change == "schema_version":
            return catalog.model_copy(update={"schema_version": "phase999"})
        if catalog_change == "catalog_version":
            return catalog.model_copy(update={"catalog": catalog.catalog.model_copy(
                update={"contract_version": "phase999"})})
        return catalog

    def changed_provider(method, dex, deadline):
        data = original_client(method, dex, deadline)
        if catalog_change == "partial" and method == "meta" and dex == "xyz":
            raise TimeoutError
        if method == "meta" and not dex:
            if catalog_change == "delisted":
                data["universe"][0]["isDelisted"] = True
            if catalog_change == "precision":
                data["universe"][0]["szDecimals"] = 3
        return data

    async def forbidden(*args, **kwargs):
        pytest.fail("invalid catalog dispatched research")
    monkeypatch.setattr(executor, "execute", forbidden)
    monkeypatch.setattr(discovery, "catalog", changed_catalog)
    if catalog_change == "missing":
        discovery.enabled = False
    if catalog_change in {"delisted", "precision", "partial"}:
        discovery._client = changed_provider
        discovery._expires = 0
    response = await client.post(f"{URL}/run", json={**proposal, "expected": binding})
    assert response.status_code == http and response.json()["reason"] == reason


async def test_start_deadline_and_completion_after_expiry(api_client, monkeypatch):
    client, discovery, _, _ = api_client
    proposal = proposal_for(evidence()).model_dump(mode="json")
    observed = discovery._clock()
    deadline = observed + timedelta(seconds=60)
    # Capture observations first, then evaluate just inside their validity window.
    discovery._clock = lambda: observed
    await discovery.catalog()
    discovery._clock = lambda: deadline - timedelta(microseconds=1)
    preview = await client.post(f"{URL}/eligibility", json=proposal)
    assert preview.status_code == 200 and datetime.fromisoformat(preview.json()["valid_until"]) == deadline
    run = dict(proposal, expected=preview.json()["binding"])

    worker_now = [deadline]

    class WorkerClock(datetime):
        @classmethod
        def now(cls, tz):
            return worker_now[0]

    monkeypatch.setattr(paper, "datetime", WorkerClock)
    calls = []
    original = SimulationEngine.run

    async def completes_after_expiry(self, **kwargs):
        calls.append(worker_now[0])
        worker_now[0] = deadline + timedelta(seconds=1)
        return await original(self, **kwargs)
    monkeypatch.setattr(SimulationEngine, "run", completes_after_expiry)
    stale = await client.post(f"{URL}/run", json=run)
    assert stale.status_code == 503 and stale.json()["reason"] == "METADATA_STALE" and not calls

    worker_now[0] = deadline - timedelta(microseconds=1)
    completed = await client.post(f"{URL}/run", json=run)
    assert completed.status_code == 200, completed.text
    output = paper.GeneralizedPaperResult.model_validate_json(completed.content)
    assert output.started_at == calls[0] and output.started_at < output.admission.valid_until < worker_now[0]
    assert output.result.trace[0].timestamp < output.admission.profile.metadata.observed_at

    discovery._clock = lambda: deadline
    expired = await client.post(f"{URL}/run", json=run)
    assert expired.status_code == 503 and expired.json()["reason"] == "METADATA_STALE"
    assert len(calls) == 1


async def test_worker_checks_expiry_after_preflight(monkeypatch):
    record = evidence()
    proposal = proposal_for(record)
    admission, _ = admit(record, proposal)
    clock = iter((admission.valid_until - timedelta(microseconds=1), admission.valid_until))

    class WorkerClock(datetime):
        @classmethod
        def now(cls, tz):
            return next(clock)

    async def forbidden(*args, **kwargs):
        pytest.fail("expired preflight started simulation")
    monkeypatch.setattr(paper, "datetime", WorkerClock)
    monkeypatch.setattr(SimulationEngine, "run", forbidden)
    with pytest.raises(paper.PaperRejected) as denied:
        await paper.execute_paper(SimulationEngine(), proposal=proposal, metadata=record,
            network="MAINNET", max_age_seconds=60, expected=admission.binding)
    assert denied.value.admission.reason == "METADATA_STALE"


async def test_changed_proposal_and_engine_reject_old_binding(api_client, monkeypatch):
    client, _, executor, _ = api_client
    initial = proposal_for(evidence()).model_dump(mode="json")
    binding = (await client.post(f"{URL}/eligibility", json=initial)).json()["binding"]

    async def forbidden(*args, **kwargs):
        pytest.fail("altered binding dispatched research")
    monkeypatch.setattr(executor, "execute", forbidden)
    for updated, reason in (
        ({"frames": 13}, "CONFIGURATION_FINGERPRINT_MISMATCH"),
        ({"scenario": "TREND_UP"}, "CONFIGURATION_FINGERPRINT_MISMATCH"),
        ({"economics": {**initial["economics"], "maker_fee_bps": "1"}}, "PROFILE_FINGERPRINT_MISMATCH"),
        ({"identity": evidence(dex="abc").identity.model_dump(mode="json")}, "IDENTITY_MISMATCH"),
        ({"identity": evidence(network="TESTNET").identity.model_dump(mode="json")}, "NETWORK_MISMATCH"),
        ({"identity": evidence(dex="xyz", name="GOLD").identity.model_dump(mode="json")},
         "METADATA_FINGERPRINT_MISMATCH"),
    ):
        response = await client.post(f"{URL}/run", json={**initial, **updated, "expected": binding})
        assert response.json()["reason"] == reason
    monkeypatch.setattr(version, "SIMULATION_ENGINE_VERSION", "fixture-engine-version-change")
    response = await client.post(f"{URL}/run", json={**initial, "expected": binding})
    assert response.status_code == 409 and response.json()["reason"] == "CONFIGURATION_FINGERPRINT_MISMATCH"


@pytest.mark.parametrize("coordinated", [False, True])
async def test_concurrent_waiter_cancel_and_shutdown_preserve_single_worker(api_client, infrastructure, monkeypatch,
                                                                         coordinated):
    client, _, local, _ = api_client
    infra, _ = infrastructure
    executor = CoordinatedSimulationExecutor(local, infra, lambda: ("test-process", "test-session")) if coordinated else local
    monkeypatch.setattr(main.app.state, "simulation_executor", executor)
    proposal = proposal_for(evidence()).model_dump(mode="json")
    binding = (await client.post(f"{URL}/eligibility", json=proposal)).json()["binding"]
    payload = {**proposal, "expected": binding}
    started, release, completed = Event(), Event(), Event()
    calls = []
    original = SimulationEngine.run

    async def slow(self, **kwargs):
        calls.append(kwargs["dataset"].fingerprint)
        started.set()
        assert await asyncio.to_thread(release.wait, 6)
        result = await original(self, **kwargs)
        completed.set()
        return result

    monkeypatch.setattr(SimulationEngine, "run", slow)
    waiter = asyncio.create_task(client.post(f"{URL}/run", json=payload))
    shutdown = None
    try:
        assert await asyncio.to_thread(started.wait, 3)
        assert (await client.post(f"{URL}/run", json=payload)).status_code == 429
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert (await client.post(f"{URL}/run", json=payload)).status_code == 429
        shutdown = asyncio.create_task(executor.shutdown())
        await asyncio.sleep(0)
        assert not shutdown.done()
        assert (await client.post(f"{URL}/run", json=payload)).status_code == 429
    finally:
        release.set()
        if shutdown is not None:
            await shutdown
    assert completed.is_set() and len(calls) == 1
    if coordinated:
        assert await infra.call("zcard", infra.key("admission", "research")) == 0
        assert not await infra.call("keys", infra.key("reference", "*"))
