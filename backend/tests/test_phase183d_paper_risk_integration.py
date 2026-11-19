import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from threading import Event

import httpx
import pytest
from eth_account import Account
from hyperliquid.exchange import Exchange

from app import main
from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
from app.market_data.market_universe_discovery import MarketUniverseDiscovery
from app.risk.authorization import FinalQuoteAuthorization
from app.simulation.engine import SimulationEngine
from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.generalized_market_profiles import PaperRejected, execute_paper
from test_phase182_generalized_paper import URL, admit, proposal_for
from test_phase183b_market_risk_metadata import market_wire, observation, spot_wire
from test_phase183c_market_risk_calculations import hypothetical, sourced

D = Decimal


@pytest.fixture
def offline_boundaries(monkeypatch):
    calls = []

    def prohibited(*args, **kwargs):
        calls.append("operational boundary")
        raise AssertionError("PAPER reached an operational boundary")

    targets = [
        (HyperliquidTestnetExecutionAdapter, name)
        for name in ("__init__", "_exchange_client", "submit_orders", "cancel_orders", "replace_orders")
    ] + [
        (Exchange, name) for name in ("__init__", "order", "bulk_orders", "cancel", "update_leverage")
    ] + [
        (Account, name) for name in ("from_key", "sign_message", "sign_transaction")
    ]
    for owner, name in targets:
        monkeypatch.setattr(owner, name, prohibited)
    yield
    assert calls == []


async def run_local(proposal, record, *, source=None, engine=None, **worker):
    admission, _ = admit(record, proposal, risk_source=source, evaluated_at=datetime.now(timezone.utc))
    assert admission.status == "ELIGIBLE", admission
    return await execute_paper(engine or SimulationEngine(), proposal=proposal, metadata=record,
                               network=record.identity.network, max_age_seconds=60,
                               expected=admission.binding, risk_source=source, **worker)


@pytest.mark.parametrize("dex", ["", "xyz"])
async def test_api_source_constrained_core_and_hip3_across_real_worker(monkeypatch, offline_boundaries, dex):
    calls = []

    def provider(method, dex_arg, deadline):
        calls.append((method, dex_arg))
        if method == "perpDexs":
            return [None, {"name": "xyz"}]
        if method == "spotMeta":
            return spot_wire()
        return market_wire(dex_arg, index=268 if dex_arg else 0, mode="noCross" if dex_arg else "strictIsolated")

    discovery = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=provider)
    executor = SimulationExecutor()
    monkeypatch.setattr(main.app.state, "market_universe_discovery", discovery, raising=False)
    monkeypatch.setattr(main.app.state, "simulation_executor", executor, raising=False)
    try:
        catalog = await discovery.catalog()
        record = next(m for m in catalog.catalog.records if m.identity.dex == dex)
        source = discovery.financial_observation(catalog.catalog_fingerprint, record.identity)
        proposal = proposal_for(record, price="100", research_risk=sourced(source), frames=12)
        payload = proposal.model_dump(mode="json")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://127.0.0.1") as client:
            checked = await client.post(URL + "/eligibility", json=payload)
            assert checked.status_code == 200, checked.text
            admission = checked.json()
            assert admission["risk_model"]["source_fingerprint"] == source.fingerprint()
            assert admission["risk_source_status"] == "SOURCE_OBSERVED"
            body = {**payload, "expected": admission["binding"]}
            first = await client.post(URL + "/run", json=body)
            second = await client.post(URL + "/run", json=body)
            assert first.status_code == second.status_code == 200, (first.text, second.text)
            first, second = first.json(), second.json()
            assert first["execution_mode"] == "PAPER" and first["research_risk"]["authority"] == "NONE"
            assert first["research_risk"] == second["research_risk"]
            assert first["result_fingerprint"] == second["result_fingerprint"]
            assert first["research_risk"]["final_snapshot"]["margin"]["unit"]["asset_reference"] == source.collateral.token_id
            assert first["result"]["vault"]["mode"] == "PAPER"
            assert admission["risk_model"]["readiness"]["status"] == "BLOCKED"
            assert calls.count(("spotMeta", "")) == 1

            for field, value in (("execution_eligible", True), ("exchange_margin_verified", True),
                                 ("risk_ready", True), ("source", admission["risk_model"]["source"])):
                forged = {**body, "research_risk": {**body["research_risk"], field: value}}
                response = await client.post(URL + "/run", json=forged)
                assert response.status_code == 422 and response.json()["reason"] == "CONFIGURATION_INVALID"

            changed = {**body, "research_risk": {**body["research_risk"], "capital_paper_quote": "1001"}}
            response = await client.post(URL + "/run", json=changed)
            assert response.status_code == 409 and response.json()["reason"] == "RISK_FINGERPRINT_MISMATCH"
    finally:
        await executor.shutdown()
        await discovery.close()


@pytest.mark.parametrize(("settings", "reason"), [
    (hypothetical(capital_paper_quote="0.001"), "RISK_CAPITAL_INSUFFICIENT"),
    (hypothetical(margin_mode="CROSS"), "RISK_MARGIN_MODE_UNSUPPORTED"),
    (hypothetical(leverage="50", max_leverage="50"), "RISK_LEVERAGE_UNSUPPORTED"),
])
def test_infeasible_model_fails_admission(settings, reason):
    source = observation(now=datetime.now(timezone.utc))
    proposal = proposal_for(source.metadata, price="100", research_risk=settings)
    a, prepared = admit(source.metadata, proposal, risk_source=source)
    assert a.reason == reason and prepared is None


async def test_hypothetical_path_preserves_ledger_when_model_is_non_binding(offline_boundaries):
    record = observation(now=datetime.now(timezone.utc)).metadata
    required = dict(price="100", scenario="FLASH_MOVE", frames=40,
                    economics={"model": "HYPOTHETICAL_LINEAR", "maker_fee_bps": "7",
                               "taker_fee_bps": "13", "funding_interval_seconds": 2})
    legacy = await run_local(proposal_for(record, **required), record)
    risk = await run_local(proposal_for(record, research_risk=hypothetical(capital_paper_quote="90000"), **required), record)
    assert "research_risk" not in legacy.model_dump() and "research_risk" not in legacy.proposal.model_dump()
    assert risk.result.fills == legacy.result.fills
    assert len(risk.result.fills) > 1
    assert risk.result.vault.fees_quote > 0 and risk.result.vault.funding_quote != 0
    assert risk.result.accounting_fingerprint == legacy.result.accounting_fingerprint
    assert risk.result.accounting_ledger == legacy.result.accounting_ledger
    assert sum(D(f["size"]) * (1 if f["side"] == "BID" else -1) for f in risk.result.fills) == risk.result.vault.position_base
    assert risk.result.run_fingerprint != legacy.result.run_fingerprint
    with localcontext(prec=60):
        assert risk.research_risk.final_snapshot.margin.capital == D(90000) + risk.result.vault.net_pnl_quote


async def test_margin_can_reduce_and_retire_quotes_without_bypassing_authorization(monkeypatch, offline_boundaries):
    from app.simulation import engine

    record = observation(now=datetime.now(timezone.utc)).metadata
    events = []
    authorize = engine.authorize

    def capture(quotes, *args, **kwargs):
        authorization = authorize(quotes, *args, **kwargs)
        assert isinstance(authorization, FinalQuoteAuthorization) and kwargs["generalized_paper"]
        events.append(tuple(quote.size for quote in quotes))
        return authorization

    monkeypatch.setattr(engine, "authorize", capture)
    legacy = await run_local(proposal_for(record, price="100"), record)
    assert legacy.result.trace[0].risk_state == "NORMAL"
    for capital, retires in (("600", False), ("300", True)):
        proposal = proposal_for(record, price="100", research_risk=hypothetical(
            initial_margin_fraction="1", capital_paper_quote=capital))
        result = await run_local(proposal, record)
        frames = result.research_risk.frames
        assert any(frame.state == "REDUCE" for frame in frames), frames
        if retires:
            assert any(frame.margin_retired_quotes and frame.authorized_quotes == 0 for frame in frames), frames
            assert not result.result.fills
        else:
            assert any(frame.authorized_quotes > 0 for frame in frames), frames
            assert sum(events[12]) < sum(events[0])
    assert len(events) == 36


async def test_stricter_existing_firewall_halt_retains_recovery_rule(offline_boundaries, monkeypatch):
    from app.risk.firewall import RiskFirewall

    evaluate = RiskFirewall.evaluate

    def initial_venue_uncertainty(self, **inputs):
        inputs["venue_uncertain"] = self.version == 0
        return evaluate(self, **inputs)

    monkeypatch.setattr(RiskFirewall, "evaluate", initial_venue_uncertainty)
    record = observation(now=datetime.now(timezone.utc)).metadata
    proposal = proposal_for(record, price="100", scenario="FLASH_MOVE", frames=40)
    control = await run_local(proposal, record)
    risk = await run_local(proposal_for(record, price="100", scenario="FLASH_MOVE", frames=40,
                                       research_risk=hypothetical(capital_paper_quote="90000")), record)
    existing = [point.risk_state for point in control.result.trace]
    modeled = [frame.state for frame in risk.research_risk.frames]
    assert existing[:4] == ["HALT", "HALT", "HALT", "NORMAL"] and existing == modeled
    assert all(frame.authorized_quotes == 0 for frame in risk.research_risk.frames if frame.state == "HALT")


async def test_modeled_maintenance_breach_halts_local_quotes(offline_boundaries, monkeypatch):
    from app.risk.firewall import RiskFirewall

    decisions = []
    evaluate = RiskFirewall.evaluate

    def capture(self, **inputs):
        decision = evaluate(self, **inputs)
        decisions.append(decision)
        return decision

    monkeypatch.setattr(RiskFirewall, "evaluate", capture)
    record = observation(now=datetime.now(timezone.utc)).metadata
    proposal = proposal_for(record, price="100", scenario="HIGH_VOLATILITY", frames=20,
                            research_risk=hypothetical(initial_margin_fraction="1",
                                                       maintenance_margin_fraction="1", capital_paper_quote="700"))
    result = await run_local(proposal, record)
    halted = [frame for frame in result.research_risk.frames if frame.state == "HALT"]
    assert halted and all(not frame.authorized_quotes for frame in halted)
    assert any("PAPER modeled maintenance headroom exhausted" in decision.reasons for decision in decisions)
    assert result.result.fills and not result.research_risk.execution_eligible


async def test_retired_source_generation_is_rejected_before_engine(monkeypatch, offline_boundaries):
    source = observation(now=datetime.now(timezone.utc))
    record = source.metadata
    proposal = proposal_for(record, price="100", research_risk=sourced(source))
    a, _ = admit(record, proposal, risk_source=source, catalog_fingerprint="a" * 64)
    engine = SimulationEngine()

    async def must_not_run(**kwargs):
        pytest.fail("retired evidence reached simulation")

    monkeypatch.setattr(engine, "run", must_not_run)
    with pytest.raises(PaperRejected, match="RISK_SOURCE_STALE"):
        await execute_paper(engine, proposal=proposal, metadata=record, network="MAINNET", max_age_seconds=60,
                            expected=a.binding, risk_source=source, catalog_valid_until=a.valid_until,
                            catalog_guard=lambda: False)
    new = observation(now=source.metadata.observed_at, raw=market_wire(table=5, leverage=5))
    recheck, _ = admit(record, proposal, risk_source=new, expected=a.binding, catalog_fingerprint="a" * 64)
    assert recheck.reason == "RISK_FINGERPRINT_MISMATCH"


async def test_cancelled_request_keeps_worker_slot_and_snapshot(offline_boundaries, monkeypatch):
    source = observation(now=datetime.now(timezone.utc))
    record = source.metadata
    proposal = proposal_for(record, price="100", research_risk=sourced(source))
    a, _ = admit(record, proposal, risk_source=source, catalog_fingerprint="b" * 64)
    started, release, retired, completed = Event(), Event(), Event(), Event()
    original = SimulationEngine.run

    async def blocked(self, **kwargs):
        started.set()
        assert await asyncio.to_thread(release.wait, 5)
        result = await original(self, **kwargs)
        assert kwargs["paper_risk_run"].model.source_fingerprint == source.fingerprint()
        completed.set()
        return result

    monkeypatch.setattr(SimulationEngine, "run", blocked)
    inputs = dict(proposal=proposal, metadata=record, network="MAINNET", expected=a.binding, max_age_seconds=60,
                  catalog_guard=lambda: not retired.is_set(), catalog_valid_until=a.valid_until, risk_source=source)
    executor = SimulationExecutor()
    try:
        task = asyncio.create_task(executor.execute("run_generalized_paper", **inputs))
        assert await asyncio.to_thread(started.wait, 5)
        retired.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ResearchBusyError):
            await executor.execute("run_generalized_paper", **inputs)
    finally:
        release.set()
        await executor.shutdown()
    assert completed.is_set()
