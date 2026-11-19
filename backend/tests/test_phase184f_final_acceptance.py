"""Independent Decimal reconciliation and coordinator publication boundaries."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
from math import ceil, floor
from statistics import median
from threading import Event

import pytest

from app.agents.advisory_contracts import AdvisorySnapshot
from app.agents.supervisor import AgentSupervisor
from app.risk.firewall import RiskFirewall
from app.simulation import engine
from test_phase182_generalized_paper import admit
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401
from test_phase183ef_risk_api import risk_api  # noqa: F401
from test_phase184d_quote_economics import evaluate, options, scenario_run, wrap
from test_phase184e_advisory_api import ADVISORY, advisory_api, paper_run  # noqa: F401

D = Decimal
F = Fraction
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def independent_economics(run, trace, assumptions):
    _, prepared = admit(run.admission.profile.metadata, run.proposal, evaluated_at=run.admission.evaluated_at)
    frames = {frame.timestamp: frame for frame in prepared.dataset.frames}
    orders = [order for order in run.result.orders if datetime.fromisoformat(order["created_at"]) == trace.timestamp]
    order_ids = {order["client_order_id"] for order in orders}
    fills = [fill for fill in run.result.fills if fill["client_order_id"] in order_ids]
    maker, taker = F(run.proposal.economics.maker_fee_bps), F(run.proposal.economics.taker_fee_bps)

    def reference(timestamp):
        frame = frames[timestamp]
        values = [frame.reference_prices.redstone, frame.perp_context.oracle_price, frame.reference_prices.kraken]
        assert all(value is not None for value in values)
        with localcontext() as context:
            context.prec = 28
            middle = median(values)
            assert all(abs(value - middle) * 10_000 / middle < 30 for value in values)
        return F(middle)

    def bp(value, *, cost=False):
        scaled = value * 10_000 * 100_000_000
        return D(ceil(scaled) if cost else floor(scaled)).scaleb(-8)

    buy = max(F(order["price"]) for order in orders if order["side"] == "BID")
    sell = min(F(order["price"]) for order in orders if order["side"] == "ASK")
    denominator = capture = entries = adverse = residual = total = F(0)
    last_fill = trace.timestamp
    for fill in fills:
        at = datetime.fromisoformat(fill["timestamp"])
        last_fill = max(last_fill, at)
        qty, execution = F(fill["size"]), F(fill["price"])
        side = 1 if fill["side"] == "BID" else -1
        ref = reference(at)
        future = next(point for point in run.result.trace if point.timestamp >= at + timedelta(seconds=5))
        denominator += qty * ref
        capture += qty * side * (ref - execution)
        entries += qty * execution * (maker if fill["liquidity"] == "MAKER" else taker) / 10_000
        adverse += max(F(0), qty * side * (ref - F(future.mid)))
        residual += qty * side
        total += qty
    frame = frames[last_fill]
    carry_at = last_fill - EPOCH
    seconds = carry_at.days * 86_400 + carry_at.seconds
    interval = run.proposal.economics.funding_interval_seconds
    settlements = (seconds + assumptions.holding_seconds) // interval - seconds // interval
    funding = residual * F(frame.perp_context.mark_price) * F(frame.perp_context.funding_rate) * settlements
    slip = F(assumptions.exit_slippage_bps) / 10_000
    close_ref = reference(last_fill)
    close_execution = close_ref * (1 - slip if residual > 0 else 1 + slip)
    exit_fee = abs(residual) * close_execution * (maker if assumptions.closing_liquidity == "MAKER" else taker) / 10_000
    inventory_after = F(next(point.inventory_base for point in run.result.trace if point.timestamp == last_fill))
    expansion = max(F(0), abs(inventory_after) - abs(inventory_after - residual))
    inventory = (expansion * F(frame.perp_context.mark_price) * F(run.result.metrics.max_inventory_utilization)
                 * F(assumptions.inventory_rate_bps) / 10_000)
    slip_amount = abs(residual) * close_ref * slip
    costs = [bp(value / denominator, cost=True) for value in (entries + exit_fee, funding, inventory, adverse, slip_amount)]
    executed = bp(capture / denominator)
    return dict(submitted_bid=buy, submitted_ask=sell, gross_spread_bps=bp((sell - buy) / reference(trace.timestamp)),
                captured_spread_bps=executed, fee_cost_bps=costs[0], funding_cost_bps=costs[1],
                inventory_cost_bps=costs[2], adverse_selection_cost_bps=costs[3], slippage_cost_bps=costs[4],
                break_even_capture_bps=sum(costs), modeled_edge_bps=executed - sum(costs),
                attributed_fill_count=len(fills), matured_markout_count=len(fills), residual_base=residual,
                filled_base=total, executed_reference_notional=denominator, entry_fees_quote=entries,
                exit_fees_quote=exit_fee, inventory_expansion_base=expansion)


@pytest.mark.parametrize("liquidity", ["MAKER", "TAKER"])
async def test_real_worker_ledger_reconciles_independently(liquidity, offline_boundaries):
    run = await scenario_run("HIGH_VOLATILITY", fees=("7", "13"))
    assumptions = options(holding_seconds=17, closing_liquidity=liquidity, exit_slippage_bps="13",
                          inventory_rate_bps="197")
    ready = []
    for trace in run.result.trace:
        output = evaluate(wrap(run, sequence=trace.sequence, options=assumptions))
        if output.status != "READY":
            continue
        expected = independent_economics(run, trace, assumptions)
        assert {field: getattr(output, field) for field in expected} == expected
        ready.append(output)
    assert len(ready) >= 2
    assert any(row.residual_base > 0 for row in ready) and any(row.residual_base < 0 for row in ready)
    assert any(row.modeled_edge_bps < 0 for row in ready)


async def test_publication_uses_current_clock_and_no_trading_authority(advisory_api, monkeypatch):
    client, _, _, request, records, _, _, _ = advisory_api
    run = await paper_run(client, records["xyz"])
    before = run.json()["result_fingerprint"], run.json()["result"]["run_fingerprint"]
    publication = []
    original = AdvisorySnapshot.validate_at

    def validate(snapshot, *, as_of):
        publication.append((snapshot.context.evaluated_at, as_of))
        return original(snapshot, as_of=as_of)

    def prohibited(*_args, **_kwargs):
        pytest.fail("Advisory research entered the trading or supervisor path")

    monkeypatch.setattr(AdvisorySnapshot, "validate_at", validate)
    monkeypatch.setattr(AgentSupervisor, "evaluate", prohibited)
    monkeypatch.setattr(RiskFirewall, "evaluate", prohibited)
    monkeypatch.setattr(engine, "authorize", prohibited)
    raw = await client.post(ADVISORY, json=request("xyz", "DISCOVERY", funding_mode="OBSERVED"))
    assert raw.status_code == 200, raw.text
    assert len(publication) == 1 and publication[0][1] > publication[0][0]
    assert raw.json()["snapshot"]["funding_basis"]["status"] == "READY"
    assert (run.json()["result_fingerprint"], run.json()["result"]["run_fingerprint"]) == before


async def test_cancellation_preserves_shared_bounded_provider_call(advisory_api):
    client, _, coordinator, request, _, _, calls, provider = advisory_api
    started, release = Event(), Event()

    def wait():
        started.set()
        assert release.wait(5)

    provider["xyz"] = wait
    body = request("xyz", "FUNDING_BASIS")
    cancelled = asyncio.create_task(client.post(ADVISORY, json=body))
    survivor = None
    try:
        assert await asyncio.to_thread(started.wait, 5)
        survivor = asyncio.create_task(client.post(ADVISORY, json=body))
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert len(coordinator._observations._tasks) == 1
    finally:
        release.set()
    assert (await survivor).json()["snapshot"]["funding_basis"]["status"] == "READY"
    assert len(calls) == 3
    await coordinator.close()
    assert not coordinator._observations._tasks and not coordinator._observations._cache
