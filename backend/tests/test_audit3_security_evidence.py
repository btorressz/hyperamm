"""Audit 3.0 corrected counterexamples and focused evidence-boundary regressions."""
from datetime import timedelta
from decimal import Decimal as D

import pytest

from app.accounting.service import AccountingService
from app.agents import AgentConfig, AgentSupervisor, AgentTelemetryStore, transform_quotes
from app.agents.evidence import build_agent_evidence
from app.agents.ml_features import FeatureUnavailableError, build_feature_vector
from app.agents.model_artifact import LogisticModelArtifact
from app.agents.predictive_adverse_selection import PredictiveAdverseSelectionAgent
from app.execution.models import Fill, OrderRequest
from app.execution.paper import PaperExecutionAdapter
from app.execution.research import PaperExecutionAssumptions
from app.market_data.history import MarketObservation, MarketPriceHistory
from app.market_data.mock import MockMarketDataAdapter
from app.references.models import ProviderStatus
from app.research.ml.dataset import build_dataset, OfflineDataset
from app.risk.firewall import RiskFirewallConfig
from app.simulation.config import SimulationConfig
from app.simulation.engine import SimulationEngine
from app.simulation.scenarios import generate_scenario
from app.strategy.models import StrategyConfig
from test_agent_expansion import T0, artifact, feature_evidence, offline_dataset
from test_phase9_agents import quote


def target():
    return MarketObservation(sequence=1, timestamp=T0+timedelta(seconds=5), mid_price=D(3002))


def dataset(evidence, fills, **kwargs):
    return build_dataset(market='ETH', evidence=[evidence], fills=fills,
                         observations=[target()], source_fingerprint='a'*64, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['BASELINE', 'MODELED_CROSSING'])
async def test_actual_paper_fill_to_telemetry_to_simulated_dataset(mode):
    # Same real adapter/order/book as A3-001, now with the correct assertion.
    telemetry = AgentTelemetryStore()
    assumptions = PaperExecutionAssumptions() if mode == 'BASELINE' else PaperExecutionAssumptions(mode=mode)
    adapter = PaperExecutionAdapter(clock=lambda:T0, assumptions=assumptions)
    adapter.on_fill = lambda fill: telemetry.observe_fill(fill, None)
    snap = MockMarketDataAdapter().snapshot_for(0)
    snap.book.timestamp = T0
    adapter.update_market(snap, evidence_at=T0, evidence_key='audit-book')
    await adapter.submit_orders([OrderRequest(client_order_id='audit-modeled', market='ETH',
        side='BID', price=D(3001), size=D('.1'))])
    raw, observed = adapter.fills.all()[0], telemetry.fills(10)[0]
    assert raw.execution_mode == 'PAPER' and observed.simulated is True
    assert observed.source == raw.source
    assert observed.identity == telemetry.fill_identity(raw)
    assert (observed.price, observed.size, observed.timestamp) == (raw.price, raw.size, raw.timestamp)
    result = dataset(feature_evidence(), [observed])
    assert result.simulated and result.sample_count == 1
    assert result.samples[0].fill_notional_quote == raw.price*raw.size
    assert OfflineDataset.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValueError, match='classification mismatch'):
        dataset(feature_evidence(simulated=False), [observed], simulated=False)


def venue_fill(**updates):
    return Fill(**(dict(client_order_id='venue', market='ETH', side='BID', price=D(3000),
        size=D(1), timestamp=T0, execution_mode='TESTNET', source='HYPERLIQUID TESTNET FILL') | updates))


@pytest.mark.parametrize('source', ['HYPERLIQUID TESTNET FILL', 'SIMULATED is only a venue display description'])
def test_venue_evidence_uses_mode_and_never_display_prefix(source):
    fill = venue_fill(source=source)
    assert Fill.model_validate_json(fill.model_dump_json()).execution_mode == 'TESTNET'
    telemetry = AgentTelemetryStore()
    telemetry.observe_fill(fill, None)
    observed = telemetry.fills(1)[0]
    assert observed.simulated is False
    assert dataset(feature_evidence(simulated=False), [observed], simulated=False).simulated is False
    with pytest.raises(ValueError, match='classification mismatch'):
        dataset(feature_evidence(), [observed])


@pytest.mark.parametrize('updates', [
    {'execution_mode':'TESTNET','source':'SIMULATED PAPER FILL'},
    {'execution_mode':'TESTNET','source':'HYPOTHETICAL MODELED PAPER FILL:book:0'},
    {'execution_mode':'PAPER'}, {'execution_mode':'LIVE'},
])
def test_contradictory_source_mode_is_rejected(updates):
    with pytest.raises(ValueError):
        venue_fill(**updates)


def test_forged_copies_fail_before_telemetry_eviction_or_duplicate_suppression():
    telemetry = AgentTelemetryStore(max_fills=1)
    original = venue_fill()
    telemetry.observe_fill(original, None)
    before = telemetry.summary()
    for cid in ('venue', 'new'):
        forged = original.model_copy(update={'execution_mode':'PAPER','client_order_id':cid})
        with pytest.raises(ValueError, match='contradiction'):
            telemetry.observe_fill(forged, None)
        assert telemetry.summary() == before
    # Even an otherwise consistent relabel of a retained identity is a conflict.
    with pytest.raises(ValueError, match='conflicting fill evidence'):
        telemetry.observe_fill(original.model_copy(update={
            'execution_mode':'PAPER','source':'SIMULATED PAPER FILL'}), None)
    observed = telemetry.fills(1)[0]
    with pytest.raises(ValueError, match='contradiction'):
        dataset(feature_evidence(), [observed.model_copy(update={'simulated':True})])


@pytest.mark.parametrize('source', ['SIMULATED PAPER FILL', 'HYPOTHETICAL MODELED PAPER FILL:book:0'])
def test_paper_serialization_and_accounting_fingerprints_remain_legacy_compatible(source):
    fill = Fill(client_order_id='compatibility', market='ETH', side='BID', price=D(3000),
                size=D(1), timestamp=T0, source=source)
    assert 'execution_mode' not in fill.model_dump()
    assert Fill.model_validate_json(fill.model_dump_json()).execution_mode == 'PAPER'
    account = AccountingService('ETH', clock=lambda:T0)
    from app.accounting.models import fingerprint
    legacy = fill.model_dump()
    identity, fee, economics = account._fill_evidence(fill)
    assert economics == fingerprint({'fill':legacy, 'fee':fee})
    if source == 'SIMULATED PAPER FILL':
        # Captured on c05ab0b before implementation (not regenerated expectations).
        assert identity == '36b22f733888bec5256f85648d59f9b44ef1b1023485d03e809177232ced7516'
        assert economics == '0634dbaa6aa4a35d9f63a2acba024bd7edd928d17b470704ce6bb97a1ce9917d'


def prediction(evidence):
    agent = PredictiveAdverseSelectionAgent(AgentConfig())
    agent.install_artifact(artifact())
    return agent.evaluate(evidence)


def assert_unavailable(evidence, reason):
    with pytest.raises(FeatureUnavailableError, match=reason):
        build_feature_vector(evidence, 'BID')
    result = prediction(evidence)
    assert result.health.value == 'INSUFFICIENT_DATA' and result.state.value == 'UNAVAILABLE'
    assert result.metrics.bid_adverse_probability is None and result.metrics.ask_adverse_probability is None
    assert any(reason in item for item in result.reasons)
    assert result.mode.value == 'SHADOW' and result.affects_quotes is False
    with pytest.raises(FeatureUnavailableError):
        dataset(evidence, [])


def test_original_a3_003_counterexample_now_unavailable():
    ev = feature_evidence(perp_stale=True, book_timestamp=T0-timedelta(days=1))
    assert_unavailable(ev, 'perpetual context explicitly stale')


def test_optional_perpetual_window_cannot_be_future_dated():
    assert_unavailable(feature_evidence(perp_window_end=T0+timedelta(seconds=1)),
                       'perpetual observation window exceeds feature time')


@pytest.mark.parametrize('field,name', [('book_timestamp','book'),('perp_timestamp','perpetual')])
@pytest.mark.parametrize('age,reason', [(None,'timestamp unavailable'),(-1,'future-dated'),(86400,'stale')])
def test_required_market_observation_times(field, name, age, reason):
    value = None if age is None else T0-timedelta(seconds=age)
    assert_unavailable(feature_evidence(**{field:value}), f'{name} '+('observation is '+reason if age is not None else reason))


@pytest.mark.parametrize('field', ['source_timestamp','observed_at'])
@pytest.mark.parametrize('age', [None, -1, 86400])
def test_reference_receipt_cannot_refresh_obsolete_or_missing_source_time(field, age):
    ev = feature_evidence()
    refs = dict(ev.reference_provenance)
    # observed_at itself is required by PriceEvidence, so missing receipt is a typed rejection.
    if field == 'observed_at' and age is None:
        with pytest.raises(ValueError):
            refs['KRAKEN'].__class__.model_validate(refs['KRAKEN'].model_dump() | {field:None})
        return
    refs['KRAKEN'] = refs['KRAKEN'].model_copy(update={field:None if age is None else T0-timedelta(seconds=age)})
    assert_unavailable(ev.model_copy(update={'reference_provenance':refs}), 'reference')


@pytest.mark.parametrize('updates', [{'stale':True}, {'healthy':False}, {'status':ProviderStatus.STALE}])
def test_explicit_reference_unavailability_is_rejected(updates):
    ev = feature_evidence()
    refs = dict(ev.reference_provenance)
    refs['REDSTONE'] = refs['REDSTONE'].model_copy(update=updates)
    assert_unavailable(ev.model_copy(update={'reference_provenance':refs}), 'reference evidence unavailable')


@pytest.mark.parametrize('updates', [{'spread_bps':None}, {'momentum_bps':None},
    {'top_n_bid_depth_base':None}, {'max_reference_deviation_bps':None},
    {'reference_provenance':{}}, {'reference_confidence':'INSUFFICIENT'}])
def test_missing_required_features_are_unavailable(updates):
    assert_unavailable(feature_evidence(**updates), 'required')


@pytest.mark.parametrize('name,limit', [('book',5),('perpetual',10),('reference',30)])
@pytest.mark.parametrize('excess', [0, .000001])
def test_freshness_inclusive_boundary_and_one_microsecond_excess(name, limit, excess):
    ev = feature_evidence()
    timestamp = T0-timedelta(seconds=limit+excess)
    if name == 'reference':
        refs = {k:v.model_copy(update={'source_timestamp':timestamp}) for k,v in ev.reference_provenance.items()}
        ev = ev.model_copy(update={'reference_provenance':refs})
    else:
        ev = ev.model_copy(update={('book_timestamp' if name == 'book' else 'perp_timestamp'):timestamp})
    if excess:
        assert_unavailable(ev, name+' observation is stale')
    else:
        assert prediction(ev).state.value == 'PREDICTED'
        assert len(build_feature_vector(ev, 'BID').values) == 12


def test_fresh_recovery_keeps_model_hash_and_rejects_artifact_tampering():
    agent = PredictiveAdverseSelectionAgent(AgentConfig())
    model = artifact()
    agent.install_artifact(model)
    good = agent.evaluate(feature_evidence())
    stale = agent.evaluate(feature_evidence(book_timestamp=T0-timedelta(days=1)))
    recovered = agent.evaluate(feature_evidence())
    assert good.state.value == recovered.state.value == 'PREDICTED'
    assert stale.state.value == 'UNAVAILABLE'
    assert good.metrics == recovered.metrics
    assert good.model_provenance.model_sha256 == recovered.model_provenance.model_sha256
    assert LogisticModelArtifact.model_validate_json(model.model_dump_json()) == model
    with pytest.raises(ValueError, match='hash mismatch'):
        LogisticModelArtifact.model_validate(model.model_dump() | {'intercept':D(2)})


def test_offline_as_of_is_bounded_and_future_features_never_leak():
    telemetry = AgentTelemetryStore()
    fill = Fill(client_order_id='asof', market='ETH', side='BID', price=D(3000), size=D(1), timestamp=T0)
    telemetry.observe_fill(fill, None)
    old = feature_evidence(updated_at=T0-timedelta(seconds=6))
    with pytest.raises(FeatureUnavailableError, match='book observation is stale'):
        dataset(old, telemetry.fills(1))
    future = feature_evidence(updated_at=T0+timedelta(microseconds=1))
    with pytest.raises(ValueError, match='no honest matured'):
        dataset(future, telemetry.fills(1))
    assert offline_dataset().fingerprint == '11a2bff144784789e3d0ce5a9a1bc19d632ba0bca7409dcc81fba335886400bf'


def test_freshness_changes_cannot_change_supervisor_quote_authority():
    supervisor = AgentSupervisor(AgentConfig())
    supervisor.predictive_adverse_selection.install_artifact(artifact())
    ev = feature_evidence()
    kwargs = dict(telemetry=AgentTelemetryStore(), history=MarketPriceHistory(), execution_mode='PAPER')
    fresh = supervisor.evaluate(evidence=ev, **kwargs)
    stale = supervisor.evaluate(evidence=ev.model_copy(update={'book_timestamp':T0-timedelta(days=1)}), **kwargs)
    recovered = supervisor.evaluate(evidence=ev, **kwargs)
    assert fresh.predictive_adverse_selection.state.value == recovered.predictive_adverse_selection.state.value == 'PREDICTED'
    assert stale.predictive_adverse_selection.state.value == 'UNAVAILABLE'
    assert fresh.version == stale.version == recovered.version
    assert fresh.fingerprint == stale.fingerprint == recovered.fingerprint
    quotes = [quote('BID','2990'), quote('ASK','3010')]
    transformed = [transform_quotes(quotes, decision, center=D(3000), tick_size=D('.1'), size_precision=4)
                   for decision in (fresh, stale, recovered)]
    assert transformed[0] == transformed[1] == transformed[2]
    for mode in ('ACTIVE','ADVISORY'):
        with pytest.raises(ValueError):
            AgentConfig(predictive_agent_mode=mode)


@pytest.mark.asyncio
async def test_simulation_and_accounting_fingerprints_match_pre_fix_baseline():
    result = await SimulationEngine().run(dataset=generate_scenario('QUIET',frames=12),
        strategy_config=StrategyConfig(), agent_config=AgentConfig(), risk_config=RiskFirewallConfig(),
        simulation_config=SimulationConfig(max_frames=12))
    assert result.run_fingerprint == '26bde070af4f2c759f78c792dfd27e3150c072c530eec28fadb4c892c80970e6'
    assert result.dataset_fingerprint == 'b6c0db72a67b8c26ca3d9e115968945d4c3645819fa56a3ec242d32f4c2c9fbd'
    assert result.accounting_fingerprint == '0f63a3c967bb486ce134657ebe56856ce74beb77a42166b263270b56f4e5c20b'


@pytest.mark.parametrize('fault', [None, 'book', 'perpetual', 'reference'])
def test_evidence_builder_preserves_actual_source_times_and_flags(fault):
    from app.simulation.references import build_simulated_references
    from app.strategy.inventory import build_inventory_state
    from app.strategy.market_adaptation import MarketAdaptationPolicy
    frames = generate_scenario('QUIET', frames=2).frames
    frame = frames[-1]
    history = MarketPriceHistory()
    for item in frames:
        history.add_snapshot(item.market)
    refs = build_simulated_references(frame, agreement_bps=D(30), outlier_bps=D(75), version=1)
    snapshot = frame.market.model_copy(deep=True)
    perp = frame.perp_context.model_copy(deep=True)
    if fault == 'book':
        snapshot.book.timestamp -= timedelta(days=1)
        assert snapshot.latest_valid_update == frame.timestamp  # fresh envelope, obsolete book
    if fault == 'perpetual':
        perp.stale = True
    if fault == 'reference':
        refs.evidence['KRAKEN'].source_timestamp -= timedelta(days=1)
    ev = build_agent_evidence(
        market_decision=MarketAdaptationPolicy(StrategyConfig()).decision(frame.market, history),
        inventory=build_inventory_state(market='ETH', position=D(0), target=D(0), soft_limit=D(5), source='PAPER'),
        perp_context=perp, refs=refs, history=history, momentum_window=20,
        market_snapshot=snapshot, config=AgentConfig(), observed_at=frame.timestamp)
    assert ev.book_timestamp == snapshot.book.timestamp
    assert ev.perp_timestamp == perp.updated_at
    assert ev.reference_provenance['KRAKEN'].source_timestamp == refs.evidence['KRAKEN'].source_timestamp
    assert ev.reference_provenance['KRAKEN'] is not refs.evidence['KRAKEN']
    if fault:
        result = prediction(ev)
        assert result.health.value == 'INSUFFICIENT_DATA' and result.state.value == 'UNAVAILABLE'
        assert result.metrics.bid_adverse_probability is None
    else:
        assert prediction(ev).state.value == 'PREDICTED'
