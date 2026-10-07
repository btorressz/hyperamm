import copy
from datetime import datetime, timedelta, timezone
import json
import pytest
from pydantic import ValidationError
from app.config import Settings
from app.runtime import HyperAmmRuntime
from app.market_data.mock import MockMarketDataAdapter
from app.terminal.models import TerminalSnapshot
from app.terminal.service import TerminalService, aggregate_health, safe_text


async def frame():
    rt = HyperAmmRuntime(
        Settings(
            _env_file=None,
            hyperliquid_private_key="sensitive-sentinel",
            redstone_api_key="redstone-sentinel",
        )
    )
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(2))
    await rt.refresh_once()
    data = await rt._publish_terminal_snapshot()
    return rt, data


@pytest.mark.asyncio
async def test_schema_stage_exposure_decimal_metadata_and_existing_provenance():
    rt, s = await frame()
    parsed = TerminalSnapshot.model_validate(s)
    assert parsed.contract_version == "phase12-v1"
    assert parsed.emitted_at.tzinfo is not None
    assert s["strategy_quotes"] == [
        q.model_dump(mode="json") for q in rt.strategy_quotes
    ]
    assert s["agent_quotes"] == [q.model_dump(mode="json") for q in rt.agent_quotes]
    assert s["authorized_quotes"] == s["quotes"]
    assert isinstance(s["quotes"][0]["price"], str)
    assert (
        s["accounting"]["accounting_fingerprint"]
        == s["vault"]["accounting_fingerprint"]
    )
    with pytest.raises(ValidationError):
        TerminalSnapshot.model_validate({**s, "contract_version": "client-selected"})
    with pytest.raises(ValidationError):
        TerminalSnapshot.model_validate({**s, "secret": "not-a-contract-field"})
    assert "sensitive-sentinel" not in json.dumps(
        s
    ) and "redstone-sentinel" not in json.dumps(s)


@pytest.mark.asyncio
async def test_sequence_is_monotonic_across_calls_and_history_is_throttled():
    rt, s = await frame()
    a, b = await rt._publish_terminal_snapshot(), await rt._publish_terminal_snapshot()
    assert s["sequence"] < a["sequence"] < b["sequence"]
    assert s["process_id"] == a["process_id"] == b["process_id"]
    assert len(rt.terminal_service.history.query()) == 1


@pytest.mark.asyncio
async def test_observation_does_not_mutate_authorities():
    rt, _ = await frame()
    before = (
        rt.authorization.model_dump(),
        rt.accounting_service.fingerprint,
        rt.firewall.version,
        rt.agent_decision.fingerprint,
        list(rt.paper.all_orders()),
    )
    await rt._publish_terminal_snapshot()
    after = (
        rt.authorization.model_dump(),
        rt.accounting_service.fingerprint,
        rt.firewall.version,
        rt.agent_decision.fingerprint,
        list(rt.paper.all_orders()),
    )
    assert before == after


@pytest.mark.asyncio
async def test_health_never_bypasses_kill_or_consistency():
    _, data = await frame()
    data["risk_firewall"]["manual_kill_active"] = True
    assert aggregate_health(data).status == "HALTED"
    data["risk_firewall"]["manual_kill_active"] = False
    data["vault"]["execution_accounting"]["status"] = "DIVERGED"
    health = aggregate_health(data)
    assert health.subsystems["execution_accounting_consistency"].status == "HALTED"
    assert health.observational


@pytest.mark.asyncio
async def test_verified_references_and_ready_agents_are_healthy():
    _, data = await frame()
    data["reference_consensus"]["confidence_state"] = "VERIFIED"
    for k in ("regime", "toxic_flow", "execution_quality"):
        data["agents"][k]["health"] = "READY"
    health = aggregate_health(data)
    assert health.subsystems["reference_consensus"].status == "HEALTHY"
    assert health.subsystems["agents"].status == "HEALTHY"


@pytest.mark.asyncio
async def test_history_no_future_values_and_emission_clock_rollback():
    _, data = await frame()
    clock = datetime.now(timezone.utc) - timedelta(days=1)
    service = TerminalService(clock=lambda: clock)
    service.observe(copy.deepcopy(data), data["diagnostics"])
    p = service.history.query()[0]
    assert p.mid_price is None and p.mark_price is None and p.equity is None
    assert p.consensus_price is None
    first = service._last_emitted_at
    clock -= timedelta(seconds=5)
    result = service.observe(copy.deepcopy(data), data["diagnostics"])
    assert result.emitted_at == first and result.sequence > 1
    assert service.events() == [] or all(e.timestamp <= first for e in service.events())


@pytest.mark.asyncio
async def test_context_change_clears_history_and_events_without_resetting_sequence():
    _, data = await frame()
    clock = datetime.now(timezone.utc)
    service = TerminalService(clock=lambda: clock)
    first = service.observe(copy.deepcopy(data), data["diagnostics"])
    clock += timedelta(seconds=2)
    data["strategy"]["config"]["market_data_mode"] = "LIVE"
    second = service.observe(copy.deepcopy(data), data["diagnostics"])
    assert second.sequence > first.sequence and second.session_id != first.session_id
    assert len(service.history.query()) == 1


@pytest.mark.asyncio
async def test_events_bounded_deduplicated_filtered_and_redacted():
    _, data = await frame()
    clock = datetime.now(timezone.utc)
    service = TerminalService(clock=lambda: clock)
    for i in range(510):
        clock += timedelta(seconds=1)
        data["strategy"]["last_error"] = f"error {i} token=abc123"
        service.observe(copy.deepcopy(data), data["diagnostics"])
    assert len(service._events) == 500 and len(service._seen_ids) <= 1000
    events = service.events(500, "STRATEGY")
    assert events and all(e.category == "STRATEGY" for e in events)
    assert "abc123" not in json.dumps([e.model_dump(mode="json") for e in events])
    count = len(service._events)
    service.observe(copy.deepcopy(data), data["diagnostics"])
    assert len(service._events) == count
    with pytest.raises(ValueError):
        service.events(501)


def test_secret_shaped_error_messages_redacted():
    assert "abc" not in safe_text(
        "api_key=abc token:abc https://provider.invalid/?secret=abc"
    )


@pytest.mark.asyncio
async def test_process_sequence_survives_new_observer_service():
    _, data = await frame()
    first = TerminalService().observe(copy.deepcopy(data), data["diagnostics"])
    second = TerminalService().observe(copy.deepcopy(data), data["diagnostics"])
    assert second.sequence > first.sequence and second.process_id == first.process_id
    assert second.session_id != first.session_id


@pytest.mark.asyncio
async def test_testnet_truth_has_no_synthetic_fill_economics_or_consistency():
    rt, _ = await frame()
    from app.accounting import AccountingService
    from app.strategy.models import ExecutionMode

    rt.config = rt.config.model_copy(update={"execution_mode": ExecutionMode.TESTNET})
    rt.strategy.config = rt.config
    rt.accounting_service = AccountingService("ETH", "TESTNET")
    s = await rt._publish_terminal_snapshot()
    assert s["fills"] == []
    assert s["execution_summary"]["fill_count"] is None
    assert s["execution_summary"]["filled_notional"] is None
    assert not s["execution_summary"]["fill_history_available"]
    assert s["vault"]["execution_accounting"]["status"] == "UNAVAILABLE"
    assert s["vault"]["net_pnl_quote"] is None


@pytest.mark.asyncio
async def test_current_payload_order_and_fill_bound_is_explicit():
    _, data = await frame()
    from app.execution.models import StrategyOrder, Fill
    from decimal import Decimal as D

    data["orders"] = [
        StrategyOrder(
            client_order_id=str(i),
            market="ETH",
            side="BID",
            price=D("3000"),
            size=D("1"),
        ).model_dump(mode="json")
        for i in range(300)
    ]
    data["fills"] = [
        Fill(
            client_order_id=str(i),
            market="ETH",
            side="BID",
            price=D("3000"),
            size=D("1"),
        ).model_dump(mode="json")
        for i in range(300)
    ]
    s = TerminalService().observe(data, data["diagnostics"])
    assert len(s.orders) == 200 and len(s.fills) == 100
    assert s.execution_summary["active_orders_truncated"]
    assert s.execution_summary["fill_count"] == 300
    assert s.execution_summary["filled_notional"] == "900000"
