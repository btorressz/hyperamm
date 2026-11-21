"""Reconcile qualified PAPER economics from execution evidence and scenario inputs."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext

import pytest

from app.amm.models import AmmModel
from app.risk.models import RiskStatus
from app.simulation import engine
from app.simulation.market_profiles import validate_price
from app.strategy.quote_engine import QuoteEngine
from test_phase183b_market_risk_metadata import market_wire, observation
from test_phase183c_market_risk_calculations import hypothetical, sourced
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401
from test_phase185d_asset_paper import FEES_AND_FUNDING, assess_asset, asset_proposal, run_asset


@pytest.mark.parametrize("risk_mode", ["default", "hypothetical", "source"])
@pytest.mark.parametrize(("model", "coin", "dex", "reference"), [
    (AmmModel.CONSTANT_PRODUCT, "DOGE", "", "0.1234"),
    (AmmModel.CONCENTRATED, "xyz:GOLD", "xyz", "2500"),
])
async def test_qualified_paper_quotes_and_ledger_reconcile(
    model, coin, dex, reference, risk_mode, monkeypatch, offline_boundaries,
):
    # Existing risk fixtures supply qualified metadata. The reference remains an explicit PAPER input.
    raw = market_wire(
        dex, coin=coin, index=268 if dex else 0, mode="noCross" if dex else "strictIsolated",
    )
    raw["universe"][0]["szDecimals"] = 3 if dex else 2
    source = observation(dex=dex, raw=raw, now=datetime.now(timezone.utc))
    record = source.metadata
    risk = {
        "default": None,
        "hypothetical": hypothetical(capital_paper_quote="10000"),
        "source": sourced(source, capital_paper_quote="10000"),
    }[risk_mode]
    proposal = asset_proposal(record, price=reference, frames=40, scenario="HIGH_VOLATILITY",
                              settings={"amm_model": model}, economics=FEES_AND_FUNDING, research_risk=risk)
    binding = {"risk_source": source} if risk_mode == "source" else {}
    admission, prepared = assess_asset(record, proposal, **binding)
    assert admission.status == "ELIGIBLE", admission.reason

    proposed, stages = [], []
    generate = QuoteEngine.generate_perp_market_adaptive
    authorize = engine.authorize

    def capture_proposal(self, *args, **kwargs):
        output = generate(self, *args, **kwargs)
        proposed.append(tuple(output[2]))
        return output

    def capture_final(quotes, references, decision, *args, **kwargs):
        authorization = authorize(quotes, references, decision, *args, **kwargs)
        # Admission also generates proposals. Pair only the live engine frames
        # that advance to the actual authorization call.
        stages.append((proposed[-1], tuple(quotes)))
        if not decision.allow_quotes:
            assert not quotes and not authorization.authorized
        elif quotes:
            assert authorization.authorized
        return authorization

    monkeypatch.setattr(QuoteEngine, "generate_perp_market_adaptive", capture_proposal)
    monkeypatch.setattr(engine, "authorize", capture_final)
    result = (await run_asset(record, proposal, admission, **binding)).result
    assert len(stages) == len(result.trace) == 40
    assert any(raw for raw, _ in stages) and any(final for _, final in stages)
    strategy = prepared.strategy
    lot = D(1).scaleb(-record.sz_decimals)
    distance_limit = RiskStatus().max_quote_distance_bps
    for frame, (raw, authorized) in zip(prepared.dataset.frames, stages, strict=True):
        assert {(q.side, q.level_index) for q in authorized} <= {(q.side, q.level_index) for q in raw}
        # Inventory policy may enlarge the reducing side before the final
        # qualified PAPER budget clamps both sides back to the declared limit.
        for quotes, side_budget in ((raw, strategy.total_liquidity * strategy.max_inventory_size_multiplier),
                                    (authorized, strategy.total_liquidity)):
            bids = sorted((q for q in quotes if q.side == "BID"), key=lambda q: q.level_index)
            asks = sorted((q for q in quotes if q.side == "ASK"), key=lambda q: q.level_index)
            assert all(a.price >= b.price for a, b in zip(bids, bids[1:]))
            assert all(a.price <= b.price for a, b in zip(asks, asks[1:]))
            assert not bids or not asks or bids[0].price < asks[0].price
            assert all(sum(q.size for q in side) <= side_budget for side in (bids, asks))
            assert sum(q.size for q in quotes) <= 2 * side_budget
            assert all(q.size >= lot and q.size % lot == 0 and q.price > 0 for q in quotes)
        for quote in authorized:
            assert quote.price * quote.size >= proposal.minimum_order_notional
            assert validate_price(quote.price, record.sz_decimals)
            midpoint = frame.market.mid_price
            assert abs(quote.price - midpoint) * 10000 <= midpoint * distance_limit

    assert result.vault.initial_equity_quote == prepared.simulation.initial_equity_quote
    reconcile_ledger(result, prepared.dataset.frames, D("7"), D("13"))


def reconcile_ledger(result, frames, maker_bps, taker_bps):
    vault = result.vault
    fills = Counter((f["client_order_id"], datetime.fromisoformat(f["timestamp"]), f["side"],
                     D(f["price"]), D(f["size"]), f["liquidity"]) for f in result.fills)
    funding_frames = {f.timestamp: f.perp_context for f in frames if f.timestamp.second % 2 == 0}
    ledger = tuple(reversed(result.accounting_ledger))
    assert fills and len(ledger) == vault.ledger_version < 500
    assert len({entry.event_id for entry in ledger}) == len(ledger)
    assert vault.ledger_fingerprint == ledger[-1].ledger_fingerprint
    initial = vault.initial_equity_quote
    position = trade_flow = realized = fees = funding = D(0)
    pending_fee = None
    settlements = set()

    # Compare the average-cost ledger to signed execution cash flows. The two
    # representations must give the same marked equity and carried cost basis.
    with localcontext(prec=65):
        def close(actual, expected):
            assert abs(actual - expected) <= D("1e-18"), (actual, expected)

        for sequence, entry in enumerate(ledger, start=1):
            assert entry.simulated and entry.sequence == sequence
            if sequence > 1:
                assert entry.previous_ledger_fingerprint == ledger[sequence - 2].ledger_fingerprint
            if entry.event_type == "TRADE_FILL":
                assert pending_fee is None
                prefix = (entry.source_reference, entry.timestamp, entry.side, entry.price, entry.size)
                match, = [key for key in fills if key[:5] == prefix and fills[key]]
                fills[match] -= 1
                delta = entry.size if entry.side == "BID" else -entry.size
                assert entry.position_delta_base == delta
                trade_flow -= delta * entry.price
                position += delta
                realized += entry.realized_pnl_delta
                close(entry.cash_delta_quote, entry.realized_pnl_delta)
                rate = maker_bps if match[5] == "MAKER" else taker_bps
                pending_fee = (entry.event_id, entry.price * entry.size * rate / 10000)
            elif entry.event_type == "FEE":
                trade_id, charge = pending_fee
                assert entry.source_reference == trade_id
                close(entry.fee_delta_quote, charge)
                close(entry.cash_delta_quote, -charge)
                fees += charge
                pending_fee = None
            else:
                assert entry.event_type == "FUNDING" and pending_fee is None
                assert entry.timestamp not in settlements
                settlements.add(entry.timestamp)
                context = funding_frames[entry.timestamp]
                payment = -position * context.mark_price * context.funding_rate
                close(entry.funding_delta_quote, payment)
                close(entry.cash_delta_quote, payment)
                funding += payment

            assert entry.position_base == position
            close(position * entry.average_entry_price, realized - trade_flow)
            if position == 0:
                assert entry.average_entry_price == 0
            close(entry.cash_balance_quote, initial + realized - fees + funding)
            close(entry.cumulative_realized_pnl, realized)
            close(entry.cumulative_fees, fees)
            close(entry.cumulative_funding, funding)

        assert pending_fee is None and not any(fills.values())
        assert settlements == set(funding_frames) - {frames[0].timestamp}
        assert len(settlements) > 1 and fees > 0
        assert vault.execution_accounting.execution_accounting_consistent
        assert vault.position_base == position
        close(vault.realized_pnl_quote, realized)
        close(vault.unrealized_pnl_quote, trade_flow + position * vault.mark_price - realized)
        close(vault.fees_quote, fees)
        close(vault.funding_quote, funding)
        equity = initial + trade_flow + position * vault.mark_price - fees + funding
        close(vault.equity_quote, equity)
        close(vault.net_pnl_quote, equity - initial)
        assert vault.reserved_capital_quote >= abs(position) * vault.mark_price - D("1e-18")
        close(vault.available_capital_quote, max(D(0), equity - vault.reserved_capital_quote))
