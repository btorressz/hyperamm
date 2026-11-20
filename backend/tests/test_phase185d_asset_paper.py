import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_UP, localcontext

import pytest
from pydantic import ValidationError

from app.amm.models import AmmModel, QuoteLevel
from app.simulation import engine, generalized_market_profiles as paper
from app.simulation.market_profiles import validate_price
from test_phase182_generalized_paper import URL, admit, api_client, evidence, proposal_for  # noqa: F401
from test_phase183b_market_risk_metadata import observation
from test_phase183c_market_risk_calculations import hypothetical, sourced
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401
from test_phase183ef_risk_api import risk_api  # noqa: F401
from test_phase184e_advisory_api import ADVISORY, advisory_api  # noqa: F401
from test_phase185a_asset_amm_contracts import controls
from test_phase185b_asset_mapping import policy

D = Decimal
CATALOG = "c" * 64
FEES_AND_FUNDING = {"model": "HYPOTHETICAL_LINEAR", "maker_fee_bps": "7", "taker_fee_bps": "13",
                    "funding_interval_seconds": 2}


def asset_proposal(record, *, price="100", minimum="20", catalog=CATALOG, settings=None, declaration=None, **values):
    lot = D(1).scaleb(-record.sz_decimals)
    base = (D(minimum) / D(price)).quantize(lot, rounding=ROUND_UP) + lot * 2
    mapped = controls(**{
        "levels_per_side": 2, "base_order_size": base, "total_liquidity": base * 6,
        "soft_inventory_limit_base": base * 12, "hard_inventory_limit_base": base * 24,
        "virtual_base_reserve": D("300000") / D(price), **(settings or {}),
    })
    declared = policy(record, simulated_reference_price=price, catalog_fingerprint=catalog,
                      controls=mapped, **(declaration or {}))
    return proposal_for(record, price=price, minimum_order_notional=minimum, asset_amm_policy=declared, **values)


def assess_asset(record, proposal, **kwargs):
    return admit(record, proposal, **{
        "catalog_fingerprint": CATALOG, "catalog_valid_until": record.observed_at + timedelta(seconds=60), **kwargs,
    })


async def run_asset(record, proposal, admission, **kwargs):
    return await paper.execute_paper(
        engine.SimulationEngine(), proposal=proposal, metadata=record, network=record.identity.network,
        expected=admission.binding, max_age_seconds=60, **{
            "catalog_valid_until": record.observed_at + timedelta(seconds=60), "catalog_guard": lambda: True, **kwargs,
        },
    )


@pytest.mark.parametrize(("model", "name", "dex", "precision", "price", "target"), [
    (AmmModel.CONSTANT_PRODUCT, "DOGE", "", 2, "0.1234", "5"),
    (AmmModel.CONCENTRATED, "BTC", "", 5, "60000", "0.0001"),
    (AmmModel.CONCENTRATED, "GOLD", "xyz", 3, "2500", "-0.001"),
])
async def test_asset_run_is_deterministic_and_final_quotes_conserve_liquidity(
        model, name, dex, precision, price, target, monkeypatch, offline_boundaries):
    record = evidence(name=name, dex=dex, precision=precision)
    proposal = asset_proposal(record, price=price, scenario="HIGH_VOLATILITY", frames=30,
                              settings={"amm_model": model, "target_inventory_base": target},
                              economics=FEES_AND_FUNDING)
    admission, prepared = assess_asset(record, proposal)
    assert prepared is not None, admission.reason
    declarations = proposal.asset_amm_policy
    assert admission.binding.asset_policy_fingerprint == declarations.fingerprint()
    authorize = engine.authorize
    captured = []

    def capture(quotes, refs, decision, *args, **kwargs):
        authorization = authorize(quotes, refs, decision, *args, **kwargs)
        captured.append((decision, tuple(quotes)))
        return authorization

    monkeypatch.setattr(engine, "authorize", capture)
    first = await run_asset(record, proposal, admission)
    second = await run_asset(record, proposal, admission)
    assert first.result == second.result
    assert first.result_fingerprint == second.result_fingerprint
    assert first.admission.authority == declarations.authority == "NONE"
    assert not first.admission.execution_eligible and first.execution_mode == "PAPER"
    assert paper.GeneralizedPaperResult.model_validate_json(first.model_dump_json()) == first
    assert any(quotes for _, quotes in captured)
    for decision, quotes in captured:
        if not decision.allow_quotes:
            assert not quotes
        bids = [q for q in quotes if q.side == "BID"]
        asks = [q for q in quotes if q.side == "ASK"]
        assert not bids or not asks or max(q.price for q in bids) < min(q.price for q in asks)
        for side in (bids, asks):
            assert sum(q.size for q in side) <= prepared.strategy.total_liquidity
            assert len({q.price for q in side}) == len(side)
            for q in side:
                assert q.price * q.size >= proposal.minimum_order_notional
                assert q.size == q.size.quantize(D(1).scaleb(-precision))
                assert validate_price(q.price, precision)
    assert sum(D(fill["size"]) * (1 if fill["side"] == "BID" else -1)
               for fill in first.result.fills) == first.result.vault.position_base
    assert all(entry.simulated for entry in first.result.accounting_ledger)


def test_policy_opt_in_fingerprints_and_legacy_serialization():
    record = evidence(precision=3)
    legacy = proposal_for(record, price="100", minimum_order_notional="20")
    previous, prepared = assess_asset(record, legacy)
    off, off_prepared = assess_asset(record, legacy.model_copy(update={"asset_amm_policy": None}))
    assert previous.model_dump_json() == off.model_dump_json()
    assert prepared == off_prepared
    assert "asset_amm_policy" not in legacy.model_dump() and "asset_policy_fingerprint" not in off.binding.model_dump()

    proposal = asset_proposal(record)
    first, initial = assess_asset(record, proposal)
    changed = asset_proposal(record, settings={"max_distance_bps": "120"})
    second, modified = assess_asset(record, changed)
    assert initial.strategy != modified.strategy
    assert first.binding.configuration_fingerprint != second.binding.configuration_fingerprint
    assert first.binding.profile_fingerprint == second.binding.profile_fingerprint == previous.binding.profile_fingerprint
    reject, _ = assess_asset(record, changed, expected=first.binding)
    assert reject.reason == "ASSET_POLICY_FINGERPRINT_MISMATCH"
    reject, _ = assess_asset(record, legacy, expected=first.binding)
    assert reject.reason == "ASSET_POLICY_FINGERPRINT_MISMATCH"


@pytest.mark.parametrize(("change", "reason"), [
    ("dex", "IDENTITY_MISMATCH"), ("network", "NETWORK_MISMATCH"),
    ("metadata", "METADATA_FINGERPRINT_MISMATCH"), ("catalog", "CATALOG_FINGERPRINT_MISMATCH"),
    ("stale", "METADATA_STALE"), ("delisted", "MARKET_DELISTED"),
    ("future", "CONFIGURATION_INVALID"), ("reference", "CONFIGURATION_INVALID"),
    ("unavailable_advisory", "ADVISORY_UNAVAILABLE"),
])
def test_policy_admission_requires_current_matching_evidence(change, reason):
    record = evidence(dex="xyz", name="GOLD", precision=3, listed=change != "delisted")
    replacement = {
        "dex": dict(dex="other", name="GOLD", precision=3),
        "network": dict(dex="xyz", name="GOLD", precision=3, network="TESTNET"),
        "metadata": dict(dex="xyz", name="GOLD", precision=4),
    }
    proposal = asset_proposal(record, declaration={
        "future": {"declared_at": record.observed_at + timedelta(seconds=1)},
        "unavailable_advisory": {"advisory_snapshot_fingerprint": "d" * 64},
    }.get(change))
    if change in replacement:
        proposal = proposal.model_copy(update={"asset_amm_policy": asset_proposal(
            evidence(**replacement[change])).asset_amm_policy})
    if change == "reference":
        proposal = proposal.model_copy(update={"simulated_reference_price": D("101")})
    kwargs = {"catalog_fingerprint": "e" * 64} if change == "catalog" else {}
    if change == "stale":
        kwargs["evaluated_at"] = record.observed_at + timedelta(seconds=60)
    admission, prepared = assess_asset(record, proposal, **kwargs)
    assert admission.reason == reason and prepared is None and admission.binding is None


def test_small_liquidity_min_notional_and_inventory_capacity_reject():
    record = evidence(precision=3)
    proposal = asset_proposal(record)
    original = proposal.asset_amm_policy
    for settings, minimum, reason in (
        (controls(base_order_size="0.0001"), D(20), "SIZE_UNREPRESENTABLE"),
        (original.controls, D(500), "ORDER_NOTIONAL_TOO_SMALL"),
        (controls(levels_per_side=2, base_order_size="1", total_liquidity="6",
                  soft_inventory_limit_base="4", hard_inventory_limit_base="5"),
         D(20), "RISK_EXPOSURE_INVALID"),
    ):
        changed = proposal.model_copy(update={"asset_amm_policy": original.model_copy(update={"controls": settings}),
                                              "minimum_order_notional": minimum})
        admission, prepared = assess_asset(record, changed)
        assert admission.reason == reason and prepared is None
    capital = asset_proposal(record, minimum="2000", settings={
        "total_liquidity": "600", "soft_inventory_limit_base": "1000", "hard_inventory_limit_base": "1400",
    })
    admission, prepared = assess_asset(record, capital)
    assert admission.reason == "RISK_CAPITAL_INSUFFICIENT" and prepared is None


def test_side_budget_floors_available_lots_before_subtracting():
    record = evidence(precision=3)
    admission, _ = assess_asset(record, asset_proposal(record))
    quotes = [
        QuoteLevel(side="BID", price=D(99 - level), size=D(size), level_index=level,
                   distance_bps=D(10), source_model=AmmModel.CONSTANT_PRODUCT)
        for level, size in enumerate(("0.2", "0.3"))
    ]
    budget = D("0.4999999999999999999999999999999999999999999999999999")
    normalized = admission.profile.normalize_quotes(quotes, D(100), side_liquidity=budget)
    assert [q.size for q in normalized] == [D("0.2"), D("0.299")]
    assert sum(q.size for q in normalized) <= budget

    one_lot = quotes[0].model_copy(update={"size": D("0.001")})
    for stage in ("agent", "risk"):
        reduced = one_lot.model_copy(update={
            f"pre_{stage}_size": D("0.001"), f"{stage}_size_multiplier": D("0.75"),
        })
        assert admission.profile.normalize_quotes([reduced], D(100), side_liquidity=budget) == []


@pytest.mark.parametrize("mode", ["hypothetical", "source"])
async def test_asset_policy_composes_with_existing_margin_and_accounting(mode, offline_boundaries):
    source = observation(now=datetime.now(timezone.utc))
    record = source.metadata
    settings = hypothetical(capital_paper_quote="900") if mode == "hypothetical" else sourced(source)
    proposal = asset_proposal(record, research_risk=settings, scenario="FLASH_MOVE", frames=30,
                              economics=FEES_AND_FUNDING)
    risk_source = source if mode == "source" else None
    admission, prepared = assess_asset(record, proposal, risk_source=risk_source)
    assert prepared is not None, admission.reason
    assert admission.binding.research_risk_fingerprint == admission.risk_model.fingerprint()
    run = await run_asset(record, proposal, admission, risk_source=risk_source)
    assert run.research_risk.model_fingerprint == admission.binding.research_risk_fingerprint
    assert run.research_risk.final_snapshot.exposure.signed_base == run.result.vault.position_base
    assert run.research_risk.authority == "NONE"
    snapshot = run.research_risk.final_snapshot
    with localcontext(prec=60):
        assert snapshot.margin.capital == settings.capital_paper_quote + run.result.vault.net_pnl_quote
    ledger = run.result.accounting_ledger
    assert len({entry.event_id for entry in ledger}) == len(ledger)
    fees = sum(D(fill["price"]) * D(fill["size"]) * (7 if fill["liquidity"] == "MAKER" else 13) / 10000
               for fill in run.result.fills)
    assert run.result.vault.fees_quote == fees > 0
    funding = [entry for entry in ledger if entry.event_type == "FUNDING"]
    assert funding and sum(entry.funding_delta_quote for entry in funding) == run.result.vault.funding_quote != 0
    contexts = {frame.timestamp: frame.perp_context for frame in prepared.dataset.frames}
    for entry in funding:
        context = contexts[entry.timestamp]
        assert int(entry.timestamp.timestamp()) % 2 == 0
        assert entry.funding_delta_quote == -entry.position_base * context.mark_price * context.funding_rate
    assert (admission.risk_model.source_fingerprint == source.fingerprint()) == (mode == "source")

    for settings, reason in [(hypothetical(margin_mode="CROSS"), "RISK_MARGIN_MODE_UNSUPPORTED"),
                             (hypothetical(capital_paper_quote="0.001"), "RISK_CAPITAL_INSUFFICIENT")]:
        rejected, _ = assess_asset(record, proposal.model_copy(update={"research_risk": settings}))
        assert rejected.reason == reason
    changed = proposal.model_copy(update={"asset_amm_policy": proposal.asset_amm_policy.model_copy(
        update={"research_risk_fingerprint": "b" * 64},
    )})
    rejected, _ = assess_asset(record, changed, risk_source=risk_source)
    assert rejected.reason == "RISK_FINGERPRINT_MISMATCH"


async def test_existing_firewall_halts_and_retires_an_asset_ladder(offline_boundaries, monkeypatch):
    original = engine.RiskFirewall.evaluate

    def invalidate(self, **inputs):
        if inputs["market_version"] == 4:
            inputs["research_risk_invalid"] = True
        return original(self, **inputs)

    monkeypatch.setattr(engine.RiskFirewall, "evaluate", invalidate)
    record = evidence(precision=3)
    proposal = asset_proposal(record, research_risk=hypothetical())
    admission, _ = assess_asset(record, proposal)
    run = await run_asset(record, proposal, admission)
    frames = run.research_risk.frames
    assert frames[0].authorized_quotes > 0
    assert [frame.state for frame in frames[3:7]] == ["HALT", "HALT", "HALT", "NORMAL"]
    assert all(frame.authorized_quotes == 0 for frame in frames if frame.state == "HALT")


async def test_worker_rechecks_expiry_and_catalog_retirement_after_preflight(monkeypatch):
    record = evidence(precision=3)
    proposal = asset_proposal(record)
    admission, _ = assess_asset(record, proposal)
    original = paper._preflight
    current = [record.observed_at]
    guard = [True]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current[0].astimezone(tz)

    def preflight(*args, **kwargs):
        original(*args, **kwargs)
        if retire:
            guard[0] = False
        else:
            current[0] = admission.valid_until

    async def prohibited(*args, **kwargs):
        pytest.fail("expired proposal entered simulation")

    monkeypatch.setattr(paper, "datetime", Clock)
    monkeypatch.setattr(paper, "_preflight", preflight)
    monkeypatch.setattr(engine.SimulationEngine, "run", prohibited)
    for retire in (False, True):
        current[0], guard[0] = record.observed_at, True
        with pytest.raises(paper.PaperRejected, match="METADATA_STALE"):
            await run_asset(record, proposal, admission, catalog_guard=lambda: guard[0])
    forged = admission.binding.model_copy(update={"asset_policy_fingerprint": "e" * 64})
    with pytest.raises(paper.PaperRejected, match="ASSET_POLICY_FINGERPRINT_MISMATCH"):
        await run_asset(record, proposal, admission.model_copy(update={"binding": forged}))


async def test_api_resolves_only_published_advisory_without_using_its_market_inputs(advisory_api, offline_boundaries):
    client, _, coordinator, request, records, clock, calls, _ = advisory_api
    request_body = request("xyz", "FUNDING_BASIS")
    advisory = await client.post(ADVISORY, json=request_body)
    assert advisory.status_code == 200, advisory.text
    data = advisory.json()
    assert data["snapshot"]["funding_basis"]["funding_rate"] == "0.0002"
    record = records["xyz"]
    clock[0] = datetime.now(timezone.utc)
    proposal = asset_proposal(
        record, catalog=request_body["catalog_fingerprint"], price="100",
        declaration={"advisory_snapshot_fingerprint": data["snapshot_fingerprint"],
                     "declared_at": clock[0]},
    )
    payload = proposal.model_dump(mode="json")
    wire = await client.post(URL + "/eligibility", json=payload)
    assert wire.status_code == 200, wire.text
    binding = wire.json()["binding"]
    assert binding["asset_policy_fingerprint"] == proposal.asset_amm_policy.fingerprint()
    raw = await client.post(URL + "/run", json={**payload, "expected": binding})
    assert raw.status_code == 200, raw.text
    result = paper.GeneralizedPaperResult.model_validate_json(raw.content)
    assert result.proposal.asset_amm_policy.advisory_snapshot_fingerprint == data["snapshot_fingerprint"]
    other_policy = {**payload["asset_amm_policy"], "advisory_snapshot_fingerprint": None}
    control = {**payload, "asset_amm_policy": other_policy}
    checked = await client.post(URL + "/eligibility", json=control)
    assert checked.status_code == 200, checked.text
    unlinked = await client.post(URL + "/run", json={**control, "expected": checked.json()["binding"]})
    assert unlinked.status_code == 200, unlinked.text
    assert raw.json()["result"] == unlinked.json()["result"]
    assert raw.json()["result_fingerprint"] != unlinked.json()["result_fingerprint"]
    assert len(calls) == 3

    forged = {**payload["asset_amm_policy"], "advisory_snapshot_fingerprint": "f" * 64}
    rejected = await client.post(URL + "/eligibility", json={**payload, "asset_amm_policy": forged})
    assert rejected.status_code == 503 and rejected.json()["reason"] == "ADVISORY_UNAVAILABLE"
    for field, value in [("affects_quotes", True), ("execution_mode", "TESTNET")]:
        invalid = {**payload, "asset_amm_policy": {**payload["asset_amm_policy"], field: value}}
        rejected = await client.post(URL + "/eligibility", json=invalid)
        assert rejected.status_code == 422 and rejected.json()["reason"] == "CONFIGURATION_INVALID"
    with pytest.raises(ValidationError, match="asset policy result mismatch"):
        paper.GeneralizedPaperResult.model_validate(result.model_copy(update={
            "proposal": proposal.model_copy(update={"asset_amm_policy": None}),
        }))
    snapshot, _ = coordinator.resolve_snapshot(data["snapshot_fingerprint"])
    coordinator._snapshots[data["snapshot_fingerprint"]] = (snapshot, record.observed_at)
    stale = await client.post(URL + "/eligibility", json=payload)
    assert stale.status_code == 503 and stale.json()["reason"] == "ADVISORY_STALE"


async def test_catalog_replacement_retires_asset_worker_and_old_capture(api_client, monkeypatch, offline_boundaries):
    client, discovery, worker, _ = api_client
    catalog = await discovery.catalog()
    record = next(e for e in catalog.catalog.records if not e.identity.dex)
    proposal = asset_proposal(record, price="0.1234", catalog=catalog.catalog_fingerprint)
    payload = proposal.model_dump(mode="json")
    admission = await client.post(URL + "/eligibility", json=payload)
    assert admission.status_code == 200, admission.text
    body = {**payload, "expected": admission.json()["binding"]}
    waiting, release = asyncio.Event(), asyncio.Event()
    execute, provider = worker.execute, discovery._client

    async def delayed(*args, **kwargs):
        waiting.set()
        await release.wait()
        return await execute(*args, **kwargs)

    def changed(method, dex, deadline):
        raw = provider(method, dex, deadline)
        if method == "meta" and dex == "xyz":
            raw["universe"].append({"name": "xyz:OTHER", "szDecimals": 2})
        return raw

    async def prohibited(*args, **kwargs):
        pytest.fail("retired catalog entered simulation")

    monkeypatch.setattr(worker, "execute", delayed)
    monkeypatch.setattr(engine.SimulationEngine, "run", prohibited)
    request = asyncio.create_task(client.post(URL + "/run", json=body))
    try:
        await asyncio.wait_for(waiting.wait(), 3)
        monkeypatch.setattr(discovery, "_client", changed)
        discovery._expires = 0
        replacement = await discovery.catalog()
        assert replacement.catalog_fingerprint != catalog.catalog_fingerprint
        assert record in replacement.catalog.records
    finally:
        release.set()
    stale = await request
    assert stale.status_code == 503 and stale.json()["reason"] == "METADATA_STALE"
    mismatch = await client.post(URL + "/run", json=body)
    assert mismatch.status_code == 409 and mismatch.json()["reason"] == "CATALOG_FINGERPRINT_MISMATCH"
