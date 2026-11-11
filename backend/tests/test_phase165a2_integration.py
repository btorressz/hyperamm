"""Actual admitted scenario/replay results, canonical receipts and authority isolation."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
from threading import Event

import httpx
import pytest
from pydantic import ValidationError

from app.agents.config import AgentConfig
from app.research_replay.comparison import (
    CapturedScenarioResult, ComparisonConfigSnapshot, ComparisonFoundation,
    ScenarioInputCapture, ScenarioProvenanceReceipt, capture_comparison_foundation,
)
from app.research_replay.contracts import HistoricalReplayResult, HistoricalReplayRequest, ReplaySegmentResult
from app.risk.firewall import RiskFirewallConfig
from app.simulation.config import SimulationConfig
from app.simulation.engine import SimulationEngine
from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.market_profiles import ResearchPerpMarketProfile
from app.simulation.models import stable_fingerprint
from app.simulation.service import SimulationService
from app.strategy.models import StrategyConfig
from phase1641_fixtures import admit, dataset
from test_phase162_replay import inputs, vault, replay_client
from test_phase14_research_vault import authority, proposal
from test_phase146_research_markets import market_client, research_client, demo
from test_phase152_live_streams import streams, eventually
from test_redis_infrastructure import infrastructure


async def pair(vault, tmp_path, market="BTC", *, kind="complete", scenario_market=None,
               strategy=None, agents=None, risk=None, simulation=None, selected=None, modeled=False):
    admitted = admit(vault, tmp_path / "incoming", dataset(kind, market))
    args = inputs(vault, admitted, max_frames=4, trace_max_points=4)
    if modeled:
        raw = args["request"].model_dump(mode="json")
        raw["execution"]["paper"] = dict(mode="MODELED_CROSSING", order_latency_ms=1, depth_sensitive=True)
        args["request"] = HistoricalReplayRequest.model_validate(raw)
    historical = await SimulationService().replay_history(**args)
    captured = json.loads(historical.captured_configuration_json)
    profile = ResearchPerpMarketProfile.model_validate(captured["market_profile"])
    scenario_market = scenario_market or market
    if selected is None:
        selected = profile if market == scenario_market else demo(scenario_market)
    controls = simulation or SimulationConfig.model_validate(captured["simulation"])
    if modeled and simulation is None:
        from app.execution.research import PaperExecutionAssumptions
        controls = controls.model_copy(update={"execution": PaperExecutionAssumptions()})
    scenario = await SimulationService().run_scenario(scenario="QUIET", frames=4,
        strategy=strategy or StrategyConfig(), agents=agents or AgentConfig(),
        risk=risk or RiskFirewallConfig(), simulation=controls, market_profile=selected,
        include_comparison_provenance=True)
    return CapturedScenarioResult.model_validate_json(scenario.model_dump_json()), HistoricalReplayResult.model_validate_json(historical.model_dump_json())


def foundation(scenario, historical, index=0, **kwargs):
    report = capture_comparison_foundation(scenario=scenario.result,
        scenario_provenance=scenario.provenance, historical=historical, segment_index=index, **kwargs)
    assert ComparisonFoundation.model_validate_json(report.model_dump_json()) == report
    assert not report.direct_metric_deltas_allowed
    assert not report.cross_segment_aggregation_allowed
    assert not report.matched_market_evidence_verified
    assert "SCENARIO_INPUT_CAPTURE_NOT_ENGINE_ATTESTED" in report.reasons
    return report


@pytest.mark.parametrize("market", ["BTC", "ETH", "SOL"])
async def test_real_serialized_markets_and_reproducible_capture(vault, tmp_path, market):
    scenario, historical = await pair(vault, tmp_path, market)
    report = foundation(scenario, historical)
    assert report.classification == "CONTEXT_ONLY"
    assert report.scenario.market == report.historical.market == market
    assert not report.differing_dimensions
    assert report.scenario.captured == scenario.provenance.captured
    assert report.scenario.run_fingerprint == scenario.result.run_fingerprint
    assert report.historical.original_dataset_fingerprint != report.historical.engine_dataset_fingerprint
    assert report.scenario.window_status == "TRACE_COMPLETE"
    assert historical.segments[0].fill_count == 0
    receipt = scenario.provenance
    assert ScenarioProvenanceReceipt.model_validate_json(receipt.model_dump_json()) == receipt
    assert receipt.result_fingerprint == stable_fingerprint(scenario.result.model_dump(mode="json"))
    with pytest.raises(ValidationError):
        receipt.captured.canonical_json = "{}"
    captured = receipt.captured.inputs()
    again = await SimulationService().run_scenario(scenario="QUIET", frames=4,
        **{name:getattr(captured,name) for name in type(captured).model_fields},
        include_comparison_provenance=True)
    assert again == scenario


async def test_btc_scenario_vs_eth_replay_is_incomparable(vault, tmp_path):
    scenario, historical = await pair(vault, tmp_path, "ETH", scenario_market="BTC")
    report = foundation(scenario, historical)
    assert report.classification == "INCOMPARABLE"
    assert "MARKET_MISMATCH" in report.reasons


@pytest.mark.parametrize("dimension", ["RISK", "AGENTS", "ACCOUNTING", "EXECUTION", "MARKET_PROFILE", "SIMULATION_CONTROLS"])
async def test_real_configuration_differences_do_not_authorize_deltas(vault, tmp_path, dimension):
    changes = {}
    if dimension == "RISK": changes["risk"] = RiskFirewallConfig(enabled=False)
    if dimension == "AGENTS": changes["agents"] = AgentConfig(agents_enabled=False)
    if dimension == "ACCOUNTING":
        from app.accounting.config import AccountingConfig
        changes["simulation"] = SimulationConfig(max_frames=4, trace_max_points=4,
            initial_equity_quote=Decimal("12345"), accounting=AccountingConfig(
                paper_fee_model_enabled=True, paper_funding_accounting_enabled=True,
                max_capital_utilization=Decimal("0.5")))
    if dimension == "EXECUTION": changes["modeled"] = True
    if dimension == "MARKET_PROFILE": changes["selected"] = demo("BTC")
    if dimension == "SIMULATION_CONTROLS": changes["simulation"] = SimulationConfig(max_frames=5, trace_max_points=3)
    scenario, historical = await pair(vault, tmp_path, **changes)
    report = foundation(scenario, historical)
    assert report.classification == "CONTEXT_ONLY"
    assert dimension in report.differing_dimensions
    assert dimension + "_MISMATCH" in report.reasons
    if dimension in {"RISK", "AGENTS", "ACCOUNTING", "EXECUTION", "SIMULATION_CONTROLS"}:
        assert "STRATEGY" in report.aligned_dimensions
    if dimension == "SIMULATION_CONTROLS":
        assert "ACCOUNTING" in report.aligned_dimensions and "EXECUTION" in report.aligned_dimensions


@pytest.mark.parametrize("kind", ["gap", "generation"])
async def test_each_discontinuous_segment_has_independent_capital(vault, tmp_path, kind):
    scenario, historical = await pair(vault, tmp_path, kind=kind)
    assert len(historical.segments) == 2
    for index, segment in enumerate(historical.segments):
        report = foundation(scenario, historical, index)
        assert report.historical.segment_index == index
        assert "HISTORICAL_SEGMENT_RESETS" in report.reasons
        assert segment.starting_equity == Decimal("100000")
        assert report.historical.window_start == segment.frames[0].evaluated_at


@pytest.mark.parametrize("record,limit,status", [(True,4,"TRACE_COMPLETE"), (True,2,"UNKNOWN"), (False,4,"UNKNOWN"), (True,0,"UNKNOWN")])
async def test_trace_retention_never_invents_temporal_evidence(vault, tmp_path, record, limit, status):
    scenario, historical = await pair(vault, tmp_path, simulation=SimulationConfig(
        max_frames=4, record_trace=record, trace_max_points=limit))
    report = foundation(scenario, historical)
    assert report.scenario.window_status == status
    assert (report.scenario.window_start is None) == (status == "UNKNOWN")
    assert "TEMPORAL_ALIGNMENT_UNPROVEN" in report.reasons


@pytest.mark.parametrize("domain,field,value", [
    ("agents","agents_enabled",False), ("risk","enabled",False),
    ("simulation","trace_max_points",2), ("simulation","initial_equity_quote","12345"),
])
async def test_substituted_capture_rejected_against_same_job_receipt(vault, tmp_path, domain, field, value):
    scenario, historical = await pair(vault, tmp_path)
    raw = json.loads(scenario.provenance.captured.canonical_json)
    raw[domain][field] = value
    forged = ScenarioInputCapture.model_validate(raw)
    with pytest.raises(ValueError, match="capture"):
        foundation(scenario, historical, scenario_inputs=forged)


@pytest.mark.parametrize("field,value", [("run_fingerprint","0"*64), ("dataset_fingerprint","0"*64), ("engine_version","forged-engine")])
async def test_result_changes_rejected_by_bound_receipt(vault, tmp_path, field, value):
    scenario, historical = await pair(vault, tmp_path)
    forged = scenario.model_copy(update={"result":scenario.result.model_copy(update={field:value})})
    with pytest.raises(ValueError): foundation(forged, historical)
    with pytest.raises(ValidationError): CapturedScenarioResult.model_validate_json(forged.model_dump_json())


async def test_unbound_engine_change_is_explicitly_incomparable(vault, tmp_path):
    scenario, historical = await pair(vault, tmp_path)
    report = capture_comparison_foundation(scenario=scenario.result.model_copy(update={"engine_version":"other-engine"}),
        scenario_inputs=scenario.provenance.captured.inputs(), historical=historical, segment_index=0)
    assert report.classification == "INCOMPARABLE" and "ENGINE_VERSION_MISMATCH" in report.reasons


@pytest.mark.parametrize("change", ["result", "archive", "segment", "configuration"])
async def test_forged_historical_result_and_archive_fail_closed(vault, tmp_path, change):
    scenario, historical = await pair(vault, tmp_path)
    forged = historical
    if change == "result": forged = historical.model_copy(update={"result_fingerprint":"0"*64})
    if change in {"archive", "segment"}:
        key = "simulation_result_json" if change == "archive" else "dataset_fingerprint"
        segment = historical.segments[0].model_copy(update={key:"{}" if change == "archive" else "0"*64})
        forged = historical.model_copy(update={"segments":(segment,)})
    if change == "configuration": forged = historical.model_copy(update={"captured_configuration_fingerprint":"0"*64})
    # model_copy bypasses validation to exercise the builder's boundary.
    with pytest.raises(ValueError):
        foundation(scenario, forged)


@pytest.mark.parametrize("change", ["extra", "coerced_bool", "financial_float", "invalid_risk", "profile_hash", "profile_market", "json_array"])
async def test_malformed_canonical_capture_rejected(vault, tmp_path, change):
    scenario, _ = await pair(vault, tmp_path)
    raw = json.loads(scenario.provenance.captured.canonical_json)
    if change == "extra": raw["risk"]["unexpected"] = True
    if change == "coerced_bool": raw["agents"]["agents_enabled"] = "false"
    if change == "financial_float": raw["simulation"]["initial_equity_quote"] = 100000.0
    if change == "invalid_risk": raw["risk"]["reference_halt_deviation_bps"] = "1"
    if change == "profile_hash": raw["market_profile"]["profile_fingerprint"] = "0"*64
    if change == "profile_market": raw["market_profile"]["market"] = "ETH"
    if change == "json_array": raw = []
    with pytest.raises(ValueError): ComparisonConfigSnapshot.from_payload(raw)


@pytest.mark.parametrize("market", ["BTC", "ETH", "SOL"])
@pytest.mark.parametrize("use_research", [False, True])
def test_opt_in_http_and_legacy_response_compatibility(market_client, market, use_research):
    client, rt = market_client
    before = deepcopy(authority(rt))
    body = dict(frames=4, research_market=market)
    if use_research:
        custom = proposal().model_dump(mode="json")
        custom["config"]["initial_equity_quote"] = "12345.123456789123456789"
        body["research"] = custom
    legacy = client.post("/api/v1/simulation/run", json=body)
    response = client.post("/api/v1/simulation/run", json={**body,"include_comparison_provenance":True})
    assert legacy.status_code == response.status_code == 200, response.text
    wrapped = CapturedScenarioResult.model_validate(response.json())
    assert wrapped.result.model_dump(mode="json") == legacy.json()
    captured = wrapped.provenance.captured.inputs()
    assert captured.strategy.market == market
    assert captured.strategy.execution_mode == "PAPER" and captured.strategy.market_data_mode == "DEMO"
    if use_research:
        assert captured.simulation.initial_equity_quote == Decimal("12345.123456789123456789")
        assert wrapped.result.research_configuration == proposal().model_validate(body["research"]).provenance()
    assert authority(rt) == before
    assert client.post("/api/v1/simulation/run", json={**body,"include_comparison_provenance":"true"}).status_code == 422


@pytest.mark.parametrize("cancel", [False, True])
async def test_occupied_http_worker_keeps_admitted_capture_and_cancellation_slot(vault, monkeypatch, cancel):
    from app.config import Settings
    from app.main import app
    from app.runtime import HyperAmmRuntime
    rt, worker = HyperAmmRuntime(Settings(_env_file=None)), SimulationExecutor()
    monkeypatch.setattr(app.state,"runtime",rt,raising=False)
    monkeypatch.setattr(app.state,"simulation_executor",worker,raising=False)
    original = SimulationService.run_scenario
    loop, started, release = asyncio.get_running_loop(), asyncio.Event(), Event()
    completed = []
    async def held(self, **kwargs):
        # Pause before the service captures effective inputs; HTTP admission
        # must already have detached every operational object.
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        result = await original(self, **kwargs)
        completed.append(result)
        return result
    monkeypatch.setattr(SimulationService,"run_scenario",held)
    admitted = (rt.config.model_copy(deep=True), rt.agent_config.model_copy(deep=True), rt.risk_config.model_copy(deep=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://localhost") as client:
        request = asyncio.create_task(client.post("/api/v1/simulation/run",json={"frames":4,"include_comparison_provenance":True}))
        shutdown = None
        try:
            await asyncio.wait_for(started.wait(),5)
            rt.config = rt.config.model_copy(update={"levels_per_side":4})
            rt.agent_config = AgentConfig(agents_enabled=False)
            rt.risk_config = RiskFirewallConfig(enabled=False)
            after_change = deepcopy(authority(rt))
            if cancel:
                request.cancel()
                with pytest.raises(asyncio.CancelledError): await request
            assert (await client.get("/api/v1/health")).status_code == 200
            for operation in ("run_scenario","replay_history","optimize","historical_catalog"):
                with pytest.raises(ResearchBusyError): await worker.execute(operation)
            shutdown = asyncio.create_task(worker.shutdown())
            await asyncio.sleep(0)
            assert not shutdown.done()
        finally:
            release.set()
            if not cancel:
                response = await request
                assert response.status_code == 200,response.text
            await (shutdown if shutdown else worker.shutdown())
    captured = completed[0].provenance.captured.inputs()
    assert captured.strategy == SimulationService.research_strategy(admitted[0])
    assert captured.agents == admitted[1] and captured.risk == admitted[2]
    assert authority(rt) == after_change
    assert not worker._busy and all(not t.is_alive() for t in worker._pool._threads)


@pytest.mark.parametrize("kill", [False, True])
async def test_seeded_active_operational_authority_ledger_and_storage_preserved(vault, tmp_path, replay_client, kill):
    from app.execution.models import OrderRequest
    from app.market_data.mock import MockMarketDataAdapter
    client, rt = replay_client
    frame = MockMarketDataAdapter().snapshot_for(4)
    await rt.market._accept(frame)
    await rt.refresh_once()
    await rt.paper.submit_orders([OrderRequest(client_order_id="165a2-seed",market="ETH",side="BID",
        price=frame.best_ask,size=Decimal(".1"))])
    await rt.refresh_once()
    rt.strategy.running = True
    await rt._execution_authority()
    async with rt.execution_lock:
        await rt.orders.reconcile_locked(rt.config.market,rt.quotes,rt.config.replace_tolerance_bps,rt.config.size_tolerance)
    rt.accounting_service.reserve(rt.quotes,await rt.execution.get_open_orders())
    if kill:
        await rt.activate_kill()
        await rt.refresh_once()
    before = deepcopy(authority(rt))
    signer = (id(rt.testnet),rt.testnet.private_key,rt.testnet.account_address,rt.testnet.enabled)
    scenario, historical = await pair(vault,tmp_path)
    stored = {p.name:p.read_bytes() for p in Path(vault.root).glob("*.json")}
    response = client.post("/api/v1/simulation/run",json={"frames":4,"include_comparison_provenance":True})
    assert response.status_code == 200,response.text
    foundation(CapturedScenarioResult.model_validate(response.json()),historical)
    assert authority(rt) == before
    assert signer == (id(rt.testnet),rt.testnet.private_key,rt.testnet.account_address,rt.testnet.enabled)
    assert {p.name:p.read_bytes() for p in Path(vault.root).glob("*.json")} == stored


async def test_provenance_preserves_active_phase15_subscriptions(vault, tmp_path, replay_client, streams, monkeypatch):
    from app.main import app
    service,sdk,_ = streams
    monkeypatch.setattr(app.state,"live_market_streams",service,raising=False)
    client,_ = replay_client
    queues = {m:service.subscribe(m) for m in ("BTC","ETH","SOL")}
    connection = sdk.clients[-1]
    before = (service._generation,tuple(connection.handles),{m:service.snapshot(m) for m in queues})
    try:
        for market in queues:
            scenario,historical = await pair(vault,tmp_path,market)
            response = client.post("/api/v1/simulation/run",json={"frames":4,"include_comparison_provenance":True})
            assert response.status_code == 200,response.text
            foundation(scenario,historical)
        assert sdk.clients == [connection] and not connection.closed
        assert (service._generation,tuple(connection.handles),{m:service.snapshot(m) for m in queues}) == before
        assert service._subscribers == {q:m for m,q in queues.items()}
        for m,q in queues.items():
            q.get_nowait()
            sdk.emit(m,"l2Book");sdk.emit(m,"activeAssetCtx")
        await eventually(lambda:all(service.snapshot(m).observation_status == "AVAILABLE" for m in queues))
        assert all(not q.empty() for q in queues.values())
    finally:
        for q in queues.values(): service.unsubscribe(q)


async def test_existing_redis_coordinator_mirrors_bound_receipt(infrastructure):
    from app.infrastructure.research import CoordinatedSimulationExecutor
    infra,_ = infrastructure
    worker = CoordinatedSimulationExecutor(SimulationExecutor(),infra,lambda:("165a2","session"))
    try:
        result = await worker.execute("run_scenario",scenario="QUIET",frames=4,
            strategy=StrategyConfig(),agents=AgentConfig(),risk=RiskFirewallConfig(),
            simulation=SimulationConfig(),include_comparison_provenance=True)
        keys = await infra.call("keys",infra.key("research-job","165a2","session","*"))
        status = json.loads(await infra.call("get",keys[0]))
        mirrored = json.loads(await infra.call("get",status["result_key"]))
        assert status["status"] == "COMPLETED"
        assert CapturedScenarioResult.model_validate(mirrored["result"]) == result
    finally: await worker.shutdown()


@pytest.mark.parametrize("change", ["dimensions", "reasons", "classification", "limitations", "market"])
async def test_self_consistent_comparison_hash_cannot_forge_semantics(vault, tmp_path, change):
    scenario, historical = await pair(vault,tmp_path)
    raw = foundation(scenario,historical).model_dump(mode="json")
    if change == "dimensions": raw["differing_dimensions"] = ["RISK"]
    if change == "reasons": raw["reasons"] = []
    if change == "classification": raw["classification"] = "INCOMPARABLE"
    if change == "limitations": raw["limitations"] = []
    if change == "market": raw["scenario"]["market"] = "ETH"
    raw["comparison_fingerprint"] = stable_fingerprint({k:v for k,v in raw.items() if k != "comparison_fingerprint"})
    with pytest.raises(ValidationError): ComparisonFoundation.model_validate(raw)


@pytest.mark.parametrize("change", ["receipt", "capture", "result_metrics", "result_execution", "request_frames"])
async def test_bound_archive_rejects_receipt_capture_and_result_corruption(vault, tmp_path, change):
    scenario, historical = await pair(vault,tmp_path)
    raw = scenario.model_dump(mode="json")
    if change == "receipt": raw["provenance"]["receipt_fingerprint"] = "0"*64
    if change == "capture": raw["provenance"]["captured"]["canonical_json"] = "{}"
    if change == "result_metrics": raw["result"]["metrics"]["ending_equity"] = "1"
    if change == "result_execution": raw["result"]["execution_assumptions_fingerprint"] = "0"*64
    if change == "request_frames": raw["provenance"]["requested_frames"] = 3
    with pytest.raises(ValidationError): CapturedScenarioResult.model_validate(raw)
    valid = foundation(scenario,historical)
    with pytest.raises(ValidationError):
        ComparisonFoundation.model_validate({**valid.model_dump(mode="json"),"classification":"ALIGNED"})


@pytest.mark.parametrize("domain", ["strategy", "agents", "risk", "simulation", "market_profile"])
async def test_model_copy_configuration_bypasses_fail_before_engine(domain, monkeypatch):
    values = dict(strategy=StrategyConfig(),agents=AgentConfig(),risk=RiskFirewallConfig(),
                  simulation=SimulationConfig(),market_profile=demo("ETH"))
    changes = dict(strategy={"hard_inventory_limit_base":Decimal("1")},
        agents={"agent_min_confidence":Decimal("2")},risk={"reference_halt_deviation_bps":Decimal("1")},
        simulation={"max_frames":1},market_profile={"profile_fingerprint":"0"*64})
    values[domain] = values[domain].model_copy(update=changes[domain])
    async def forbidden(*args,**kwargs):
        pytest.fail("malformed capture reached engine")
    monkeypatch.setattr(SimulationEngine,"run",forbidden)
    with pytest.raises(ValueError):
        await SimulationService().run_scenario(scenario="QUIET",frames=4,
            include_comparison_provenance=True,**values)


async def test_direct_worker_admission_detaches_mutable_inputs(monkeypatch):
    original = SimulationService.run_scenario
    loop, started, release = asyncio.get_running_loop(), asyncio.Event(), Event()
    async def held(self, **kwargs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        return await original(self,**kwargs)
    monkeypatch.setattr(SimulationService,"run_scenario",held)
    strategy,agents,risk,simulation = StrategyConfig(),AgentConfig(),RiskFirewallConfig(),SimulationConfig()
    worker = SimulationExecutor()
    job = asyncio.create_task(worker.execute("run_scenario",scenario="QUIET",frames=4,
        strategy=strategy,agents=agents,risk=risk,simulation=simulation,include_comparison_provenance=True))
    try:
        await asyncio.wait_for(started.wait(),5)
        strategy.levels_per_side=4
        agents.agents_enabled=False
        risk.enabled=False
        simulation.initial_equity_quote=Decimal("10")
    finally:
        release.set()
        result = await job
        await worker.shutdown()
    captured = result.provenance.captured.inputs()
    assert captured.strategy == StrategyConfig()
    assert captured.agents == AgentConfig() and captured.risk == RiskFirewallConfig()
    assert captured.simulation == SimulationConfig()


async def test_effective_testnet_live_inputs_adapt_before_capture(vault,tmp_path):
    operational = StrategyConfig(market_data_mode="LIVE",execution_mode="TESTNET")
    before = operational.model_dump_json()
    scenario,historical = await pair(vault,tmp_path,"SOL",strategy=operational)
    captured = scenario.provenance.captured.inputs()
    assert captured.strategy == SimulationService.research_strategy(operational,captured.market_profile)
    assert operational.model_dump_json() == before
    assert captured.strategy.market == "SOL"
    assert captured.strategy.market_data_mode == "DEMO" and captured.strategy.execution_mode == "PAPER"
    foundation(scenario,historical)


async def test_capture_normalizes_engine_accounting_capital_override():
    requested = SimulationConfig(initial_equity_quote=Decimal("4321.123456789123456789"))
    before = requested.model_dump_json()
    captured = await SimulationService().run_scenario(scenario="QUIET",frames=4,
        strategy=StrategyConfig(),agents=AgentConfig(),risk=RiskFirewallConfig(),
        simulation=requested,include_comparison_provenance=True)
    effective = captured.provenance.captured.inputs().simulation
    assert effective.accounting.paper_initial_equity_quote == effective.initial_equity_quote
    assert captured.result.metrics.starting_equity == effective.initial_equity_quote
    assert requested.model_dump_json() == before


@pytest.mark.parametrize("change", ["request_accounting", "request_precision", "origin_dataset", "segment_dataset", "segment_index"])
async def test_rehashed_historical_identity_substitution_fails(vault,tmp_path,change):
    scenario,historical = await pair(vault,tmp_path)
    raw = historical.model_dump(mode="json")
    if change == "request_accounting": raw["request"]["execution"]["accounting"]["paper_taker_fee_bps"] = "25"
    if change == "request_precision": raw["request"]["execution"]["size_decimals"] = 4
    if change == "origin_dataset": raw["request"]["dataset_fingerprint"] = "0"*64
    if change == "segment_dataset":
        segment = raw["segments"][0]
        archived = json.loads(segment["simulation_result_json"])
        archived["dataset_fingerprint"] = segment["dataset_fingerprint"] = "0"*64
        segment["simulation_result_json"] = json.dumps(archived)
        segment["simulation_result_fingerprint"] = stable_fingerprint(archived)
    if change == "segment_index": raw["segments"][0]["segment_index"] = 1
    request = HistoricalReplayRequest.model_validate(raw["request"])
    forged = historical.model_copy(update={"request":request,
        "request_fingerprint":stable_fingerprint(request),
        "modeling_fingerprint":stable_fingerprint((request.policy,request.execution)),
        "segments":tuple(ReplaySegmentResult.model_validate(s) for s in raw["segments"])})
    forged = forged.model_copy(update={"result_fingerprint":stable_fingerprint(
        forged.model_dump(exclude={"result_fingerprint"}))})
    forged = HistoricalReplayResult.model_validate_json(forged.model_dump_json())
    with pytest.raises(ValueError): foundation(scenario,forged)
