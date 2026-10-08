import copy
from datetime import datetime, timedelta, timezone
import json
import pytest
from pydantic import ValidationError
from app.config import Settings
from app.runtime import HyperAmmRuntime
from app.market_data.mock import MockMarketDataAdapter
from app.references.models import ReferenceConsensus
from app.terminal.models import TerminalSnapshot
from app.terminal.service import TerminalService, aggregate_health, safe_text, age_sources


THRESHOLDS = {"market": 5, "REDSTONE": 5, "REDSTONE_PUBLIC_HTTP": 60,
              "KRAKEN": 5, "COINGECKO": 90}


def retained_at(data, timestamp):
    """Retain healthy T0 economics without another strategy/provider evaluation."""
    data = copy.deepcopy(data)
    data["strategy"]["config"]["perp_context_stale_after_seconds"] = 5
    data["perp_context"].update(updated_at=timestamp.isoformat(), stale=False)
    for provider, e in data["references"]["evidence"].items():
        e.update(source_timestamp=timestamp.isoformat(), observed_at=timestamp.isoformat(),
                 age_ms=0, healthy=True, stale=False, status="HEALTHY", simulated=False,
                 transport="LIVE_WS" if provider in ("REDSTONE", "KRAKEN") else
                 "REST" if provider == "COINGECKO" else "NATIVE")
    for c in (data["reference_consensus"], data["references"]["consensus"]):
        c.update(updated_at=timestamp.isoformat(), confidence_state="VERIFIED",
                 eligible_providers=["REDSTONE", "HYPERLIQUID_ORACLE", "KRAKEN"])
    return data


def observe_at(data, now, thresholds=None):
    service = TerminalService(clock=lambda: now)
    snapshot = service.observe(data, data["diagnostics"],
                               freshness_thresholds=thresholds or THRESHOLDS)
    return snapshot, service.history.query()[0]


@pytest.mark.asyncio
async def test_retained_sources_age_at_fresh_terminal_emission_without_redeciding():
    _, data = await frame()
    t0 = datetime.now(timezone.utc)
    data = retained_at(data, t0)
    original = copy.deepcopy(data)
    s, h = observe_at(data, t0 + timedelta(seconds=40))
    assert s.emitted_at == t0 + timedelta(seconds=40)
    assert s.perp_context["stale"]
    assert s.system_health.subsystems["perp_context"].status == "DEGRADED"
    assert h.strategy_reference_price is h.mark_price is h.oracle_price is None
    kraken = s.references.evidence["KRAKEN"]
    assert kraken.age_ms == 40000 and kraken.stale and not kraken.healthy
    assert kraken.source_timestamp == t0 and kraken.observed_at == t0
    assert kraken.status == "HEALTHY"  # Last provider state is distinct.
    cg = s.references.evidence["COINGECKO"]
    assert cg.age_ms == 40000 and cg.healthy and not cg.stale
    assert s.reference_consensus == ReferenceConsensus.model_validate(original["reference_consensus"])
    assert s.references.consensus == ReferenceConsensus.model_validate(original["references"]["consensus"])
    assert s.reference_consensus.confidence_state == "VERIFIED"
    assert s.references.consensus.confidence_state == "VERIFIED"
    assert s.system_health.subsystems["reference_consensus"].status == "DEGRADED"
    assert s.system_health.subsystems["redstone_transport"].status == "DEGRADED"
    assert "Last provider state HEALTHY" in s.system_health.subsystems["redstone_transport"].reason
    assert h.consensus_price is None
    assert data == original


@pytest.mark.asyncio
@pytest.mark.parametrize("transport,stale", [("LIVE_WS", True), ("PUBLIC_HTTP", False)])
async def test_redstone_uses_retained_transport_budget(transport, stale):
    _, data = await frame()
    t0 = datetime.now(timezone.utc)
    data = retained_at(data, t0)
    data["references"]["evidence"]["REDSTONE"]["transport"] = transport
    s, _ = observe_at(data, t0 + timedelta(seconds=40))
    red = s.references.evidence["REDSTONE"]
    assert red.age_ms == 40000 and red.stale == stale and red.healthy != stale
    assert red.transport == transport and red.source_timestamp == t0


@pytest.mark.asyncio
async def test_demo_evidence_uses_simulated_observation_budget_not_live_provider_budget():
    _, data = await frame()
    t0 = datetime.now(timezone.utc)
    data = retained_at(data, t0)
    for e in data["references"]["evidence"].values():
        e.update(transport="DEMO", simulated=True)
    s, _ = observe_at(data, t0 + timedelta(seconds=40))
    assert all(e.stale and not e.healthy and e.age_ms == 40000
               for e in s.references.evidence.values())


@pytest.mark.asyncio
async def test_native_context_and_midpoint_use_their_distinct_active_budgets():
    _, data = await frame()
    t0 = datetime.now(timezone.utc)
    data = retained_at(data, t0)
    data["strategy"]["config"]["perp_context_stale_after_seconds"] = 60
    s, h = observe_at(data, t0 + timedelta(seconds=40))
    assert not s.perp_context["stale"] and h.mark_price is not None
    for provider in ("HYPERLIQUID_MARK", "HYPERLIQUID_ORACLE"):
        assert s.references.evidence[provider].healthy
        assert not s.references.evidence[provider].stale
    assert s.references.evidence["HYPERLIQUID_MID"].stale


@pytest.mark.asyncio
async def test_new_provider_observed_at_does_not_refresh_retained_price_timestamp():
    _, data = await frame()
    t0 = datetime.now(timezone.utc)
    data = retained_at(data, t0)
    now = t0 + timedelta(seconds=40)
    data["references"]["evidence"]["KRAKEN"]["observed_at"] = now.isoformat()
    data["references"]["evidence"]["KRAKEN"]["age_ms"] = 0
    s, _ = observe_at(data, now)
    e = s.references.evidence["KRAKEN"]
    assert e.observed_at == now and e.source_timestamp == t0
    assert e.age_ms == 40000 and e.stale and not e.healthy


@pytest.mark.asyncio
async def test_fresh_degraded_consensus_and_unrelated_stale_tertiary_source():
    _, data = await frame()
    t0 = datetime.now(timezone.utc)
    data = retained_at(data, t0)
    for c in (data["reference_consensus"], data["references"]["consensus"]):
        c["confidence_state"] = "DEGRADED"
    data["references"]["evidence"]["COINGECKO"]["source_timestamp"] = (t0 - timedelta(seconds=100)).isoformat()
    s, h = observe_at(data, t0 + timedelta(seconds=1))
    assert s.references.evidence["COINGECKO"].stale
    assert s.reference_consensus.confidence_state == "DEGRADED"
    assert h.consensus_price == s.reference_consensus.consensus_price
    assert h.mark_price is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["missing", "future", "naive", "invalid"])
async def test_invalid_source_times_cannot_gain_health_from_zero_age(problem):
    _, data = await frame()
    t0 = datetime.now(timezone.utc)
    data = retained_at(data, t0)
    bad = {"missing": None, "future": (t0 + timedelta(seconds=40)).isoformat(),
           "naive": t0.replace(tzinfo=None).isoformat(), "invalid": "not-a-timestamp"}[problem]
    data["perp_context"]["updated_at"] = bad
    data["references"]["evidence"]["KRAKEN"]["source_timestamp"] = bad
    # Invalid wire timestamps may fail contract validation; freshness must already
    # fail closed before that validation rather than becoming healthy at age zero.
    age_sources(data, t0, THRESHOLDS)
    assert data["perp_context"]["stale"]
    e = data["references"]["evidence"]["KRAKEN"]
    assert e["age_ms"] == 0 and e["stale"] and not e["healthy"]
    assert aggregate_health(data, t0).subsystems["reference_consensus"].status != "HEALTHY"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,transport,offset,stale", [
    ("KRAKEN", "LIVE_WS", 5, False), ("KRAKEN", "LIVE_WS", 5.001, True),
    ("REDSTONE", "LIVE_WS", 2, False), ("REDSTONE", "PUBLIC_HTTP", 0.001, True),
    ("HYPERLIQUID_ORACLE", "NATIVE", 0.001, True),
])
async def test_existing_provider_future_tolerance_is_preserved(provider, transport, offset, stale):
    _, data = await frame()
    t0 = datetime.now(timezone.utc)
    data = retained_at(data, t0)
    e = data["references"]["evidence"][provider]
    e.update(transport=transport, source_timestamp=(t0 + timedelta(seconds=offset)).isoformat())
    s, _ = observe_at(data, t0)
    assert s.references.evidence[provider].stale == stale
    assert s.references.evidence[provider].healthy != stale


@pytest.mark.asyncio
async def test_runtime_aging_publication_preserves_exact_authority_and_provider_state(monkeypatch):
    rt, _ = await frame()
    t0 = rt.perp_context.updated_at
    # Populate provider state even in DEMO to detect accidental sampler mutation.
    for provider in (rt.reference_service.redstone, rt.reference_service.kraken, rt.reference_service.coingecko):
        provider.state.enabled = True
        provider.state.accept("3000", t0, observed_at=t0)

    def authority():
        return copy.deepcopy({
            "perp": rt.perp_context.model_dump(),
            "perp_service": vars(rt.perp_context_service),
            "references": rt.references.model_dump(),
            "reference_version": rt.reference_service._version,
            "reference_fingerprint": rt.reference_service._fingerprint,
            "redstone_effective_version": rt.reference_service.redstone._effective_version,
            "redstone_effective_fingerprint": rt.reference_service.redstone._effective_fingerprint,
            "redstone_public_http": {k: v for k, v in vars(rt.reference_service.redstone.public_http.state).items()
                                     if k != "on_update"},
            "providers": [{k: v for k, v in vars(p.state).items() if k != "on_update"}
                          for p in (rt.reference_service.redstone, rt.reference_service.kraken, rt.reference_service.coingecko)],
            "risk": rt.risk_decision.model_dump(), "risk_version": rt.firewall.version,
            "authorization": rt.authorization.model_dump(),
            "authorization_fingerprint": rt.authorization.authorization_fingerprint,
            "quote_fingerprint": rt.authorization.quote_fingerprint,
        })

    def forbidden(*args, **kwargs):
        raise AssertionError("observation must not evaluate trading/provider services")

    before = authority()
    for service in (rt.perp_context_service, rt.reference_service, rt.reference_service.redstone,
                    rt.reference_service.kraken, rt.reference_service.coingecko):
        monkeypatch.setattr(service, "snapshot", forbidden)
    monkeypatch.setattr(rt.reference_service.consensus_policy, "evaluate", forbidden)
    rt.terminal_service.clock = lambda: t0 + timedelta(seconds=40)
    queue = rt.subscribe_terminal()
    await rt._publish_terminal_snapshot()
    wire = json.loads(queue.get_nowait())
    assert wire["emitted_at"] == (t0 + timedelta(seconds=40)).isoformat().replace("+00:00", "Z")
    assert wire["perp_context"]["stale"] and not wire["references"]["evidence"]["KRAKEN"]["healthy"]
    # Instance monkeypatch attributes are test instrumentation, not authority.
    after = authority()
    after["perp_service"].pop("snapshot", None)
    assert before == after
    rt.unsubscribe_terminal(queue)


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


PUBLIC_SECRET_CASES = [
    "Authorization: Bearer SYNTHETIC_VALUE",
    "authorization: bearer SYNTHETIC_VALUE",
    "AUTHORIZATION = Bearer    SYNTHETIC_VALUE",
    "Authorization: Basic SYNTHETIC_VALUE",
    "Proxy-Authorization: Bearer SYNTHETIC_VALUE",
    "Authorization=Bearer SYNTHETIC_VALUE",
    "api_key=SYNTHETIC_VALUE", "api-key: SYNTHETIC_VALUE",
    "x-api-key: SYNTHETIC_VALUE", "token=SYNTHETIC_VALUE",
    "token: SYNTHETIC_VALUE", "access_token=SYNTHETIC_VALUE",
    "secret=SYNTHETIC_VALUE", "client_secret = SYNTHETIC_VALUE",
    "private_key: SYNTHETIC_VALUE",
    "https://provider.invalid/?token=SYNTHETIC_VALUE",
    "https://provider.invalid/?api_key=SYNTHETIC_VALUE",
    "https://user:SYNTHETIC_VALUE@provider.invalid/path",
    "wss://provider.invalid/?token=SYNTHETIC_VALUE",
    '"Authorization": "Bearer SYNTHETIC_VALUE"',
    "token='SYNTHETIC_VALUE with spaces'",
    'Authorization: Bearer "SYNTHETIC_VALUE with spaces"',
]


@pytest.mark.parametrize("text", PUBLIC_SECRET_CASES)
def test_public_diagnostic_complete_credential_redaction(text):
    result = safe_text("retry failed; " + text + "; reconnect pending")
    assert "SYNTHETIC_VALUE" not in json.dumps(result)
    assert "retry failed" in result and "reconnect pending" in result
    assert len(result) <= 500
    assert safe_text(result) == result


def test_authorization_value_is_entirely_redacted_before_bounding():
    assert safe_text("Authorization: Bearer SYNTHETIC_VALUE") == "Authorization: [REDACTED]"
    assert safe_text("Authorization=Bearer abc.def.ghi") == "Authorization=[REDACTED]"
    assert len(safe_text("x" * 600)) == 500
    assert "SYNTHETIC_VALUE" not in safe_text("x" * 480 + " Authorization: Bearer SYNTHETIC_VALUE")
    assert "0x" + "a" * 64 not in safe_text("private key " + "0x" + "a" * 64)
    assert safe_text(RuntimeError("rate limit; token=SYNTHETIC_VALUE")) == "rate limit; token=[REDACTED]"


def test_diagnostic_container_recursion_preserves_domain_strings():
    from app.diagnostics import sanitize_public_payload
    payload = {"error": {"detail": "Authorization: Bearer SYNTHETIC_VALUE",
                         "metadata": [{"unexpected": "token=SYNTHETIC_VALUE"}]},
               "market": "token=market-name", "source_id": "https://source.invalid/id",
               "fingerprint": "token=fingerprint", "transport": "LIVE_WS"}
    original = copy.deepcopy(payload)
    result = sanitize_public_payload(payload)
    assert "SYNTHETIC_VALUE" not in json.dumps(result)
    for field in ("market", "source_id", "fingerprint", "transport"):
        assert result[field] == payload[field]
    assert payload == original


@pytest.mark.asyncio
async def test_nested_diagnostic_snapshot_event_and_rest_serialization():
    import httpx
    from fastapi import FastAPI
    from app.api import risk, terminal, strategy, agents, accounting
    rt, data = await frame()
    secret = "Authorization: Bearer SYNTHETIC_VALUE"
    data["venue_reconciliation"]["error"] = {"detail": secret, "metadata": [{"opaque": secret}]}
    data["strategy"]["last_error"] = secret
    service = TerminalService()
    snapshot = service.observe(data, data["diagnostics"])
    snapshot_wire = json.dumps(snapshot.model_dump(mode="json"))
    event_wire = json.dumps([e.model_dump(mode="json") for e in service.events(500)])
    assert "SYNTHETIC_VALUE" not in snapshot_wire
    assert "SYNTHETIC_VALUE" not in event_wire
    assert service.events(500)
    # Independent REST routes must not depend on prior terminal publication.
    evidence = rt.references.evidence["REDSTONE"]
    rt.references.evidence["REDSTONE"] = evidence.model_copy(update={"error": secret})
    rt.strategy.last_error = secret
    rt.risk.last_reason = secret
    before = copy.deepcopy((rt.references, rt.strategy, rt.risk, rt.authorization))
    rt.terminal_service = service
    app = FastAPI()
    app.state.runtime = rt
    for module in (risk, terminal, strategy, agents, accounting):
        app.include_router(module.router, prefix="/api/v1")
    responses = {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/references", "/risk/evidence", "/terminal/events", "/risk",
                     "/risk/events", "/risk/authorization", "/strategy", "/agents", "/vault"):
            response = await client.get("/api/v1" + path)
            assert response.status_code == 200, response.text
            assert "SYNTHETIC_VALUE" not in response.text
            responses[path] = response.json()
    assert "[REDACTED]" in json.dumps(responses["/references"])
    queue = rt.subscribe_terminal()
    await rt._publish_terminal_snapshot()
    assert "SYNTHETIC_VALUE" not in queue.get_nowait()
    rt.unsubscribe_terminal(queue)
    assert (rt.references, rt.strategy, rt.risk, rt.authorization) == before
