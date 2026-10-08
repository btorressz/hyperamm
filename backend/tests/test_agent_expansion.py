from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import json

import pytest
from pydantic import ValidationError

from app.agents import AgentConfig, AgentSupervisor, AgentTelemetryStore, transform_quotes
from app.agents.evidence import FillObservation
from app.agents.liquidity_quality import LiquidityQualityAgent
from app.agents.perp_crowding import PerpCrowdingAgent
from app.agents.regime import RegimeAgent
from app.agents.toxic_flow import ToxicFlowAgent
from app.agents.execution_quality import ExecutionQualityAgent
from app.agents.ml_features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, FeatureSchema, FeatureVector, build_feature_vector
from app.agents.model_artifact import LogisticModelArtifact, load_model_artifact
from app.agents.models import (AgentEvidenceSnapshot, AgentHealth, PredictiveAgentMode,
    PredictiveAdverseSelectionMetrics, semantic_fingerprint)
from app.agents.predictive_adverse_selection import PredictiveAdverseSelectionAgent
from app.agents.snapshot import AgentSystemSnapshot
from app.execution.models import Fill, OrderStatus, StrategyOrder
from app.market_data.history import MarketPriceHistory, MarketObservation
from app.research.ml.dataset import build_dataset, validate_independent_windows, OfflineDataset
from app.research.ml.validation import PredictionOutcome, evaluate_predictions
from test_phase9_agents import evidence, history, quote, snapshot

T0 = datetime(2001, 1, 1, tzinfo=timezone.utc)


def feature_evidence(**updates):
    values = dict(updated_at=T0, spread_bps=D(4),top_n_bid_depth_base=D(10),
        top_n_ask_depth_base=D(10),depth_imbalance=D(0),depth_concentration=D('.1'),midpoint_instability_bps=D(0))
    values.update(updates)
    if values.get('open_interest_change_ratio') is not None or values.get('funding_rate_delta') is not None:
        values.setdefault('perp_observation_count',2)
        values.setdefault('perp_window_start',values['updated_at']-timedelta(seconds=10))
        values.setdefault('perp_window_end',values['updated_at'])
    return evidence(**values)



def artifact(side_weight="1", horizon="5"):
    coefficients = [D(0)]*len(FEATURE_NAMES)
    coefficients[-1] = D(side_weight)
    return LogisticModelArtifact.seal(coefficients=coefficients, intercept=D(0), provenance=dict(
        model_name="test-logistic",model_version="1",model_type="LOGISTIC_REGRESSION",
        feature_schema_version=FEATURE_SCHEMA_VERSION,training_dataset_fingerprint="1"*64,
        validation_dataset_fingerprint="2"*64,training_config_fingerprint="3"*64,trained_at=T0+timedelta(days=4),
        training_window_start=T0,training_window_end=T0+timedelta(days=1),
        validation_window_start=T0+timedelta(days=2),validation_window_end=T0+timedelta(days=3),
        training_sample_count=20,validation_sample_count=10,validation_metrics={"brier_score":D(".25")},
        library_version="test",market="ETH",simulated=True,markout_horizon_seconds=D(horizon)))


@pytest.mark.parametrize("updates",[
    {"toxic_flow_markout_horizons_seconds":(5,1)}, {"toxic_flow_markout_horizons_seconds":(1,1)},
    {"toxic_flow_markout_horizons_seconds":(1,5,15,30)}, {"toxic_flow_markout_horizons_seconds":(float('nan'),)},
    {"liquidity_thin_depth_base":D('Infinity')}, {"crowding_funding_threshold":D(0)},
    {"predictive_agent_mode":"ACTIVE"}, {"predictive_agent_mode":"ADVISORY"},
    {"perp_observation_window":121}, {"agent_max_spread_multiplier":D(11)},
    {"perp_min_observation_span_seconds":D(1000)},
])
def test_expanded_config_rejects_unbounded_and_active_options(updates):
    with pytest.raises(ValueError): AgentConfig(**updates)


def test_regime_v2_uses_normalized_stress_combinations_and_inventory():
    agent = RegimeAgent(AgentConfig())
    normal = agent.evaluate(feature_evidence(volatility_score=D(0)))
    stressed = agent.evaluate(feature_evidence(funding_rate=D('.0005'),mark_oracle_basis_bps=D(30),inventory_ratio=D(1)))
    assert normal.state.value == 'QUIET'
    assert stressed.state.value == 'DISLOCATED'
    assert stressed.funding_stress_score == stressed.basis_stress_score == stressed.inventory_stress_score == 1
    assert stressed.spread_multiplier >= normal.spread_multiplier
    assert stressed.bid_size_multiplier <= normal.bid_size_multiplier
    assert stressed.bid_size_multiplier == stressed.ask_size_multiplier


@pytest.mark.parametrize('field', ['spread_bps','open_interest_change_ratio','funding_rate_delta','midpoint_instability_bps'])
def test_expanded_evidence_rejects_nonfinite(field):
    data=feature_evidence().model_dump();data[field]=D('NaN')
    with pytest.raises(ValueError): AgentEvidenceSnapshot.model_validate(data)


def test_toxic_v2_horizons_frozen_and_statistics_decimal():
    telemetry=AgentTelemetryStore()
    telemetry.observe_fill(Fill(client_order_id='horizons',market='ETH',side='BID',price=D(3000),size=D(2),timestamp=T0),None)
    h=history(['3000','2997','2994','2991'],start=T0,step=5)
    c=AgentConfig(toxic_flow_min_matured_fills=1)
    output=ToxicFlowAgent(c).evaluate(feature_evidence(updated_at=T0+timedelta(seconds=15)),telemetry,h)
    assert [m.horizon_seconds for m in output.metrics.horizons]==[1,5,15]
    assert output.metrics.markout_1s_bps==output.metrics.markout_5s_bps==D(-10)
    assert output.metrics.markout_15s_bps==D(-30)
    assert output.metrics.median_markout_bps==D(-10)
    assert output.metrics.toxicity_persistence==1
    assert output.metrics.notional_weighted_toxicity==1
    selected=[telemetry.markouts(h,horizon_seconds=seconds,window=10)[0] for seconds in (1,5,15)]
    for i in range(20): h.add_snapshot(snapshot('3200',i+5,T0+timedelta(seconds=i+16)))
    assert selected==[telemetry.markouts(h,horizon_seconds=seconds,window=10)[0] for seconds in (1,5,15)]
    assert all(isinstance(x,D) for x in (output.metrics.recency_weighted_toxicity,output.metrics.bid_confidence))


def test_recency_and_notional_weights_have_separate_deterministic_meanings():
    telemetry=AgentTelemetryStore()
    for cid,size,time in [('old','10',0),('recent','1',60)]:
        telemetry.observe_fill(Fill(client_order_id=cid,market='ETH',side='BID',price=D(3000),size=D(size),timestamp=T0+timedelta(seconds=time)),None)
    h=MarketPriceHistory()
    for seq,(time,price) in enumerate([(0,'3000'),(5,'2997'),(60,'3000'),(65,'3003'),(75,'3003')],1):
        h.add_snapshot(snapshot(price,seq,T0+timedelta(seconds=time)))
    result=ToxicFlowAgent(AgentConfig(toxic_flow_min_matured_fills=1)).evaluate(feature_evidence(updated_at=T0+timedelta(seconds=75)),telemetry,h)
    assert result.metrics.recency_weighted_toxicity < result.metrics.notional_weighted_toxicity
    assert 0 <= result.metrics.bid_confidence <= 1


def test_unresolved_horizon_eviction_is_terminally_counted_and_memory_bounded():
    telemetry=AgentTelemetryStore(max_fills=1)
    for i in range(2):
        telemetry.observe_fill(Fill(client_order_id=str(i),market='ETH',side='BID',price=D(3000),size=D(1),timestamp=T0),None)
    assert telemetry.summary()['evicted_unavailable_markouts']==3
    assert len(telemetry.fills(1000))==1
    for horizon in (2,3,4,6,7): telemetry.markouts(MarketPriceHistory(),horizon_seconds=horizon,window=1)
    with pytest.raises(ValueError,match='eight'): telemetry.markouts(MarketPriceHistory(),horizon_seconds=8,window=1)


@pytest.mark.parametrize('state,updates',[
    ('INSUFFICIENT_DATA',{'top_n_bid_depth_base':None}),
    ('HEALTHY',{}), ('THIN',{'top_n_bid_depth_base':D('.2')}),
    ('IMBALANCED',{'depth_imbalance':D('.9')}),
    ('UNSTABLE',{'midpoint_instability_bps':D(40),'volatility_score':D('.8')}),
    ('DISLOCATED',{'reference_confidence':'CONFLICTED'}),
])
def test_liquidity_quality_states_conservative(state,updates):
    data=feature_evidence().model_dump();data.update(updates)
    result=LiquidityQualityAgent(AgentConfig()).evaluate(AgentEvidenceSnapshot(**data))
    assert result.state.value==state
    assert result.spread_multiplier>=1 and result.bid_size_multiplier<=1 and result.ask_size_multiplier<=1


def test_imbalance_only_reduces_more_on_crowded_book_side():
    result=LiquidityQualityAgent(AgentConfig()).evaluate(feature_evidence(depth_imbalance=D('.9')))
    assert result.bid_size_multiplier < result.ask_size_multiplier <= 1


def test_perp_history_requires_distinct_source_timestamps_and_bounded_span():
    from app.simulation.scenarios import generate_scenario
    telemetry=AgentTelemetryStore(max_perp_observations=3)
    context=generate_scenario('QUIET',frames=2).frames[0].perp_context.model_copy(update={'updated_at':T0,'open_interest_base':D(100)})
    assert telemetry.observe_perp(context)
    for _ in range(10): assert not telemetry.observe_perp(context.model_copy(update={'version':100}))
    kwargs=dict(now=T0,window=3,min_span_seconds=D(5),max_span_seconds=D(900))
    assert telemetry.perp_changes(**kwargs)['open_interest_change_ratio'] is None
    assert telemetry.observe_perp(context.model_copy(update={'updated_at':T0+timedelta(seconds=10),'open_interest_base':D(110)}))
    kwargs['now']=T0+timedelta(seconds=10)
    assert telemetry.perp_changes(**kwargs)['open_interest_change_ratio']==D('.1')
    kwargs['now']=T0+timedelta(seconds=1000)
    assert telemetry.perp_changes(**kwargs)['open_interest_change_ratio'] is None
    for i in range(4): telemetry.observe_perp(context.model_copy(update={'updated_at':T0+timedelta(seconds=20+i)}))
    assert telemetry.summary()['perp_observations']==3


@pytest.mark.parametrize('sign,side,state',[(1,'BID','LONG_CROWDED'),(-1,'ASK','SHORT_CROWDED')])
def test_crowding_requires_combination_and_reduces_only_relevant_side(sign,side,state):
    ev=feature_evidence(funding_rate=D('.0006')*sign,mark_oracle_basis_bps=D(30)*sign,
        mark_mid_basis_bps=D(20)*sign,momentum_bps=D(30)*sign,open_interest_change_ratio=D('.1'),perp_observation_count=2)
    agent=PerpCrowdingAgent(AgentConfig())
    out=agent.evaluate(ev)
    assert out.state.value==state
    assert getattr(out,side.lower()+'_size_multiplier')<1
    assert getattr(out,('ask' if side=='BID' else 'bid')+'_size_multiplier')==1
    funding_only=agent.evaluate(feature_evidence(funding_rate=D('.0006')*sign,open_interest_change_ratio=D(0)))
    assert funding_only.state.value=='NEUTRAL'
    assert funding_only.spread_multiplier==funding_only.bid_size_multiplier==funding_only.ask_size_multiplier==1


def test_execution_v2_uses_recorded_paper_lifecycle_and_preserves_unavailable_latency():
    telemetry=AgentTelemetryStore(max_fills=1)
    order=StrategyOrder(client_order_id='filled',market='ETH',side='BID',price=D(2999),size=D(1),level_index=0,created_at=T0,updated_at=T0)
    telemetry.observe_orders([order])
    telemetry.observe_fill(Fill(client_order_id='filled',market='ETH',side='BID',price=D(2999),size=D('.5'),timestamp=T0+timedelta(seconds=1)),D(3000))
    telemetry.observe_fill(Fill(client_order_id='filled',market='ETH',side='BID',price=D(2999),size=D('.5'),timestamp=T0+timedelta(seconds=3)),D(3000))
    order.status=OrderStatus.FILLED;order.filled_size=D(1);order.updated_at=T0+timedelta(seconds=3)
    telemetry.observe_orders([order])
    m=ExecutionQualityAgent(AgentConfig(execution_quality_min_fills=1)).evaluate(feature_evidence(),telemetry,history(['3000','3001'],start=T0,step=10),'PAPER').metrics
    assert m.mean_time_to_first_fill_seconds==1 # Survives fill-window eviction.
    assert m.mean_time_to_fill_seconds==m.mean_quote_lifetime_seconds==3
    assert m.level_quality[0].fill_rate==1
    assert m.reconciliation_latency_seconds is m.venue_acknowledgment_latency_seconds is None
    testnet=ExecutionQualityAgent(AgentConfig()).evaluate(feature_evidence(simulated=False),telemetry,MarketPriceHistory(),'TESTNET').metrics
    assert testnet.mean_time_to_first_fill_seconds is testnet.mean_quote_lifetime_seconds is None
    assert testnet.level_quality==()


@pytest.mark.parametrize('agent_name',['regime','toxic_flow','execution_quality','liquidity_quality','perp_crowding','predictive_adverse_selection'])
def test_every_expanded_agent_failure_has_no_authority_or_upstream_increase(monkeypatch,agent_name):
    supervisor=AgentSupervisor(AgentConfig())
    def fail(*_): raise RuntimeError('failure')
    monkeypatch.setattr(getattr(supervisor,agent_name),'evaluate',fail)
    result=supervisor.evaluate(evidence=feature_evidence(),telemetry=AgentTelemetryStore(),history=MarketPriceHistory(),execution_mode='PAPER')
    failed=getattr(result,agent_name)
    assert failed.health==AgentHealth.ERROR
    assert (failed.spread_multiplier,failed.bid_size_multiplier,failed.ask_size_multiplier)==(1,1,1)
    for upstream in ([quote('BID','2990'),quote('ASK','3010')],[quote('ASK','3010','1',2)]):
        adapted=transform_quotes(upstream,result,center=D(3000),tick_size=D('.1'),size_precision=4)
        by_slot={(q.side,q.level_index):q for q in upstream}
        for q in adapted:
            old=by_slot[q.side,q.level_index]
            assert q.size<=old.size
            assert q.price<=old.price if q.side=='BID' else q.price>=old.price
        assert {(q.side,q.level_index) for q in adapted} <= set(by_slot)
    assert not any(hasattr(getattr(supervisor,agent_name),name) for name in ('submit_orders','cancel_orders','clear_kill','accounting','position','authorize'))


def test_shadow_identity_and_prediction_changes_are_nonmaterial():
    s=AgentSupervisor(AgentConfig());ev=feature_evidence();t=AgentTelemetryStore();h=MarketPriceHistory()
    kwargs=dict(evidence=ev,telemetry=t,history=h,execution_mode='PAPER')
    a=s.evaluate(**kwargs)
    s.predictive_adverse_selection.install_artifact(artifact('1'))
    b=s.evaluate(**kwargs)
    s.predictive_adverse_selection.install_artifact(artifact('-1'))
    c=s.evaluate(**kwargs)
    assert a.fingerprint==b.fingerprint==c.fingerprint and a.version==b.version==c.version
    assert b.predictive_adverse_selection.metrics.bid_adverse_probability != c.predictive_adverse_selection.metrics.bid_adverse_probability
    assert b.predictive_adverse_selection.model_provenance.model_sha256 != c.predictive_adverse_selection.model_provenance.model_sha256
    upstream=[quote('BID','2990'),quote('ASK','3010')]
    outputs=[transform_quotes(upstream,d,center=D(3000),tick_size=D('.1'),size_precision=4) for d in (a,b,c)]
    assert outputs[0]==outputs[1]==outputs[2]
    assert all(not d.predictive_adverse_selection.affects_quotes for d in (a,b,c))


@pytest.mark.parametrize('probability',['NaN','Infinity','-.01','1.01'])
def test_invalid_predictive_probability_rejected(probability):
    with pytest.raises(ValueError): PredictiveAdverseSelectionMetrics(bid_adverse_probability=D(probability))


def test_feature_order_missing_policy_and_artifact_hash_schema(tmp_path):
    ev=feature_evidence();vector=build_feature_vector(ev,'BID')
    assert len(vector.values)==len(FEATURE_NAMES) and vector.values[-1]==1
    with pytest.raises(ValueError): FeatureSchema(feature_names=tuple(reversed(FEATURE_NAMES)))
    with pytest.raises(ValueError): FeatureVector(feature_schema_version='unknown',values=vector.values,side='BID')
    with pytest.raises(ValueError): build_feature_vector(ev.model_copy(update={'spread_bps':None}),'BID')
    with pytest.raises(ValueError): build_feature_vector(ev.model_copy(update={'book_timestamp':T0+timedelta(seconds=1)}),'BID')
    model=artifact();raw=model.model_dump();raw['coefficients']=tuple(D(2) for _ in FEATURE_NAMES)
    with pytest.raises(ValueError,match='hash mismatch'): LogisticModelArtifact.model_validate(raw)
    raw=model.model_dump();raw['provenance']['feature_schema_version']='unknown'
    with pytest.raises(ValueError,match='schema mismatch'): LogisticModelArtifact.model_validate(raw)
    path=tmp_path/'artifact.json';path.write_text(model.model_dump_json())
    assert load_model_artifact(path)==model
    path.write_bytes(b'x'*65537)
    with pytest.raises(ValueError,match='bounded size'): load_model_artifact(path)


def test_invalid_artifact_and_missing_features_never_reuse_prediction():
    agent=PredictiveAdverseSelectionAgent(AgentConfig());agent.install_artifact(artifact())
    assert agent.evaluate(feature_evidence()).state.value=='PREDICTED'
    missing=agent.evaluate(feature_evidence().model_copy(update={'spread_bps':None}))
    assert missing.health==AgentHealth.ERROR and missing.metrics.bid_adverse_probability is None
    invalid=artifact().model_copy(update={'intercept':D('NaN')})
    with pytest.raises(ValueError): agent.install_artifact(invalid)
    assert agent.evaluate(feature_evidence()).state.value=='ERROR'
    assert agent.evaluate(feature_evidence()).metrics.bid_adverse_probability is None


def offline_dataset(start=T0, source='a', future='2997'):
    ev=feature_evidence(updated_at=start)
    telemetry=AgentTelemetryStore()
    telemetry.observe_fill(Fill(client_order_id=source,market='ETH',side='BID',price=D(3000),size=D(1),timestamp=start),None)
    return build_dataset(market='ETH',evidence=[ev],fills=telemetry.fills(1),observations=[
        MarketObservation(timestamp=start,sequence=1,mid_price=D(3000)),
        MarketObservation(timestamp=start+timedelta(seconds=5),sequence=2,mid_price=D(future))],
        source_fingerprint=semantic_fingerprint(source))


def test_dataset_future_labels_cannot_change_past_features_and_duplicates_do_not_inflate():
    first=offline_dataset();different=offline_dataset(future='3003')
    assert first.samples[0].features==different.samples[0].features
    assert first.samples[0].adverse and not different.samples[0].adverse
    ev=feature_evidence();future_ev=feature_evidence(updated_at=T0+timedelta(seconds=1),momentum_bps=D(999))
    telemetry=AgentTelemetryStore();telemetry.observe_fill(Fill(client_order_id='a',market='ETH',side='BID',price=D(3000),size=D(1),timestamp=T0),None)
    obs=[MarketObservation(timestamp=T0+timedelta(seconds=5),sequence=2,mid_price=D(2997))]
    dataset=build_dataset(market='ETH',evidence=[ev,ev,future_ev],fills=telemetry.fills(1)*2,observations=obs*2,source_fingerprint=semantic_fingerprint('a'))
    assert dataset.samples[0].features==first.samples[0].features
    assert dataset.fingerprint==first.fingerprint and dataset.sample_count==1


def test_dataset_identity_windows_include_label_maturity_and_reject_reuse():
    train=offline_dataset();validation=offline_dataset(start=T0+timedelta(seconds=10),source='b')
    validate_independent_windows(train,validation)
    assert train.time_end==T0+timedelta(seconds=5)
    with pytest.raises(ValueError,match='overlap'): validate_independent_windows(train,train)
    overlapping=offline_dataset(start=T0+timedelta(seconds=4),source='b')
    with pytest.raises(ValueError,match='overlap'): validate_independent_windows(train,overlapping)
    bad=train.model_dump();bad['samples']=bad['samples']*2;bad['sample_count']=2
    with pytest.raises(ValueError,match='duplicate'): OfflineDataset.model_validate(bad)
    bad=train.model_dump();bad['fingerprint']='0'*64
    with pytest.raises(ValueError,match='fingerprint'): OfflineDataset.model_validate(bad)


def test_probability_calibration_reports_sides_horizon_and_small_buckets():
    report=evaluate_predictions([PredictionOutcome(side='BID',probability=D('.8'),markout_bps=D(-3)),
        PredictionOutcome(side='ASK',probability=D('.2'),markout_bps=D(3)),
        PredictionOutcome(side='BID',probability=D('.5'))],partition='holdout',horizon_seconds=D(5),simulated=True)
    assert report.prediction_count==3 and report.matured_label_count==2
    assert report.metrics['accuracy']==1 and report.metrics['roc_auc']==1
    assert report.metrics['brier_score']==D('.04')
    assert report.metrics['calibration_error']==D('.2')
    assert all(not b.sufficient_samples for b in report.buckets)
    assert report.bid_metrics['accuracy']==report.ask_metrics['accuracy']==1


def test_snapshot_copies_cycle_and_rejects_mixed_evidence():
    ev=feature_evidence();supervisor=AgentSupervisor(AgentConfig());telemetry=AgentTelemetryStore()
    decision=supervisor.evaluate(evidence=ev,telemetry=telemetry,history=MarketPriceHistory(),execution_mode='PAPER')
    snapshot=AgentSystemSnapshot.capture(supervisor.config,ev,decision,telemetry,supervisor)
    before=snapshot.model_dump_json()
    decision.regime.reasons.append('later mutation')
    telemetry.observe_fill(Fill(client_order_id='new',market='ETH',side='BID',price=D(3000),size=D(1)),None)
    assert snapshot.model_dump_json()==before
    with pytest.raises(ValueError,match='cycle mismatch'):
        AgentSystemSnapshot.capture(supervisor.config,ev.model_copy(update={'market_version':999}),decision,telemetry,supervisor)


@pytest.mark.asyncio
async def test_expanded_runtime_shadow_does_not_change_financial_or_execution_authority():
    from test_phase9_runtime import prepared_runtime
    from app.risk.authorization import authorize
    rt,_=await prepared_runtime()
    from app.market_data.mock import MockMarketDataAdapter
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(4))
    await rt.refresh_once()
    rt.agent_supervisor.predictive_adverse_selection.install_artifact(artifact())
    before=rt.accounting_service.snapshot().model_dump();kill=rt.risk.kill_switch_active
    decision=rt.agent_supervisor.evaluate(evidence=rt.agent_evidence,telemetry=rt.agent_telemetry,history=rt.market_history,execution_mode='PAPER')
    assert decision.predictive_adverse_selection.state.value=='PREDICTED'
    authorization=authorize(rt.quotes,rt.references,rt.risk_decision,decision,rt.vault_snapshot)
    assert authorization.agent_fingerprint==rt.authorization.agent_fingerprint
    assert authorization.authorization_fingerprint==rt.authorization.authorization_fingerprint
    assert rt.accounting_service.snapshot().model_dump()==before and rt.risk.kill_switch_active==kill
    assert rt.paper.all_orders()==[]
    rt.strategy.running=True
    await rt._execution_authority()


def test_trusted_artifact_path_is_private_and_invalid_load_visibly_fails(tmp_path):
    from app.config import Settings
    from app.runtime import HyperAmmRuntime
    path=tmp_path/'untrusted-invalid.json';path.write_text('{broken')
    settings=Settings(_env_file=None,predictive_model_artifact_path=str(path))
    assert 'predictive_model_artifact_path' not in settings.model_dump()
    rt=HyperAmmRuntime(settings)
    output=rt.agent_supervisor.predictive_adverse_selection.evaluate(feature_evidence())
    assert output.health==AgentHealth.ERROR and str(path) not in output.model_dump_json()


def test_agent_apis_preserve_shape_filter_bounds_and_private_artifact_boundary():
    from fastapi.testclient import TestClient
    from app.main import app
    from test_api import preview_tick
    with TestClient(app) as client:
        preview_tick(client)
        before=client.get('/api/v1/agents').json()
        for key in ('regime','toxic_flow','execution_quality','supervisor','agent_version','agent_fingerprint',
                    'liquidity_quality','perp_crowding','predictive_adverse_selection'):
            assert key in before
        assert before['predictive_adverse_selection']['mode']=='SHADOW'
        assert before['predictive_adverse_selection']['affects_quotes'] is False
        assert client.get('/api/v1/agents/evidence').json()==before['evidence']
        assert client.get('/api/v1/agents/models').json()['model_provenance'] is None
        for limit in (0,251): assert client.get(f'/api/v1/agents/events?limit={limit}').status_code==422
        assert client.get('/api/v1/agents/events?agent=UNKNOWN').status_code==422
        selected=client.get('/api/v1/agents/events?agent=LIQUIDITY_QUALITY&limit=1').json()
        assert len(selected)<=1 and all(e['agent']=='LIQUIDITY_QUALITY' for e in selected)
        rt=client.app.state.runtime
        rt.agent_telemetry.observe_fill(Fill(client_order_id='after-publication',market='ETH',side='BID',price=D(3000),size=D(1)),None)
        assert client.get('/api/v1/agents').json()==before
        assert 'predictive_model_artifact_path' not in before['config']


@pytest.mark.asyncio
async def test_shadow_simulation_reuses_domain_agents_and_binds_frozen_fill_outcomes():
    from app.simulation.engine import SimulationEngine
    from app.simulation.scenarios import generate_scenario
    from app.simulation.config import SimulationConfig
    from app.strategy.models import StrategyConfig
    from app.risk.firewall import RiskFirewallConfig
    dataset=generate_scenario('HIGH_VOLATILITY',frames=60)
    config=AgentConfig(regime_min_samples=2,toxic_flow_min_matured_fills=1,execution_quality_min_fills=1)
    kwargs=dict(dataset=dataset,strategy_config=StrategyConfig(),agent_config=config,
        risk_config=RiskFirewallConfig(),simulation_config=SimulationConfig(record_trace=True))
    normal=await SimulationEngine().run(**kwargs)
    shadow=await SimulationEngine().run(**kwargs,predictive_model=artifact())
    assert normal.metrics==shadow.metrics and normal.fills==shadow.fills and normal.orders==shadow.orders
    assert shadow.run_fingerprint!=normal.run_fingerprint
    assert shadow.metrics.liquidity_quality_state_counts and shadow.metrics.perp_crowding_state_counts
    assert any(t.predictive_state=='PREDICTED' for t in shadow.trace)
    evaluation=shadow.predictive_evaluation
    assert evaluation.affects_quotes is False and evaluation.simulated is True
    assert evaluation.total_fill_predictions>0
    assert any(r.label_state=='MATURED' for r in evaluation.records)
    assert evaluation.reports[0].partition=='simulation' and evaluation.reports[0].horizon_seconds==5
    for r in evaluation.records:
        assert r.prediction_time<=r.fill_time
        if r.label_state=='MATURED': assert r.label_time>=r.fill_time+timedelta(seconds=5)


def test_offline_training_optional_import_and_real_coefficient_export():
    pytest.importorskip('sklearn')
    from app.research.ml.training import train_logistic_model,TrainingConfig
    def many(start,source):
        evs=[];fills=[];obs=[]
        for i in range(24):
            time=start+timedelta(seconds=i*10)
            evs.append(feature_evidence(updated_at=time,momentum_bps=D(20 if i%2 else -20)))
            fills.append(FillObservation(identity=f'{source}-{i}',client_order_id=f'{source}-{i}',market='ETH',side='BID',
                price=D(3000),size=D(1),timestamp=time,source='SIMULATED PAPER FILL',simulated=True))
            obs.append(MarketObservation(timestamp=time+timedelta(seconds=5),sequence=i+1,mid_price=D(2997 if i%2 else 3003)))
        return build_dataset(market='ETH',evidence=evs,fills=fills,observations=obs,source_fingerprint=semantic_fingerprint(source))
    training=many(T0,'train');validation=many(T0+timedelta(hours=1),'validate')
    model,report=train_logistic_model(training=training,validation=validation,
        config=TrainingConfig(),trained_at=T0+timedelta(days=1))
    assert report.partition=='validation' and report.matured_label_count==24
    assert model.provenance.training_dataset_fingerprint==training.fingerprint
    assert model.provenance.validation_dataset_fingerprint==validation.fingerprint
    assert model.provenance.model_sha256==LogisticModelArtifact.model_validate_json(model.model_dump_json()).provenance.model_sha256
    assert model.predict(training.samples[1].features)>model.predict(training.samples[0].features)
    with pytest.raises(ValueError,match='overlap'): train_logistic_model(training=training,validation=training)


def test_liquidity_level_cap_respects_available_upstream_evidence():
    output=LiquidityQualityAgent(AgentConfig()).evaluate(feature_evidence(top_n_bid_depth_base=D('.1'),upstream_available_levels=1))
    assert output.max_levels==1


def test_single_oi_observation_cannot_carry_a_trend():
    data=feature_evidence().model_dump();data.update(open_interest_change_ratio=D('.1'),perp_observation_count=1)
    with pytest.raises(ValueError,match='retained observation'): AgentEvidenceSnapshot.model_validate(data)


def test_relabeling_a_duplicate_fill_cannot_inflate_offline_samples():
    fill=FillObservation(identity='one',client_order_id='stable',market='ETH',side='BID',price=D(3000),size=D(1),timestamp=T0,source='SIMULATED PAPER FILL',simulated=True)
    data=build_dataset(market='ETH',evidence=[feature_evidence()],fills=[fill,fill.model_copy(update={'identity':'relabeled'})],
        observations=[MarketObservation(timestamp=T0+timedelta(seconds=5),sequence=2,mid_price=D(2997))],source_fingerprint='a'*64)
    assert data.sample_count==1
