const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const check=require(path.join(process.env.TERMINAL_TEST_BUILD,'utils/scenarioReplayComparison.js'));
const sha='a'.repeat(64);
function side(kind='SCENARIO',market='BTC'){
 return {kind,market,source_kind:kind==='SCENARIO'?'DETERMINISTIC_SCENARIO':'SYNTHETIC_FIXTURE',
 original_dataset_fingerprint:sha,engine_dataset_fingerprint:sha,
 simulation_result_fingerprint:sha,run_fingerprint:sha,engine_version:'phase10',
 frame_count:4,captured:{fingerprint:sha,strategy_fingerprint:sha,
 agents_fingerprint:sha,risk_fingerprint:sha,accounting_fingerprint:sha,
 execution_fingerprint:sha,simulation_controls_fingerprint:sha,
 market_profile_fingerprint:sha,canonical_json:'{}'},
 window_start:'2026-11-01T00:00:00.000001Z',
 window_end:'2026-11-01T00:00:00.000002Z',
 window_status:kind==='SCENARIO'?'TRACE_COMPLETE':'SEGMENT_RECEIPTS',
 segment_index:kind==='SCENARIO'?null:0,
 replay_result_fingerprint:kind==='SCENARIO'?null:sha,
 replay_segment_count:kind==='SCENARIO'?null:1,
 source_authenticated:false,licensing_independently_verified:false,
 simulated:true,read_only:true,authority:'NONE'};
}
function fixture(blocked=false){
 const foundation={version:'phase165a1-v1',classification:blocked?'INCOMPARABLE':'CONTEXT_ONLY',
 scenario:side(),historical:side('HISTORICAL_SEGMENT',blocked?'ETH':'BTC'),
 aligned_dimensions:['MARKET','ENGINE','STRATEGY','AGENTS','RISK','ACCOUNTING',
  'EXECUTION','MARKET_PROFILE','SIMULATION_CONTROLS'],
 differing_dimensions:[],reasons:['SCENARIO_AND_HISTORICAL_EVIDENCE_DIFFER',
 'SCENARIO_INPUT_CAPTURE_NOT_ENGINE_ATTESTED','TEMPORAL_ALIGNMENT_UNPROVEN',
 'HISTORICAL_LICENSING_UNVERIFIED'],direct_metric_deltas_allowed:false,
 cross_segment_aggregation_allowed:false,matched_market_evidence_verified:false,
 authority:'NONE',limitations:['separate evidence'],comparison_fingerprint:sha};
 if(blocked){foundation.aligned_dimensions=foundation.aligned_dimensions.filter(x=>x!=='MARKET');
 foundation.differing_dimensions=['MARKET'];foundation.reasons.push('MARKET_MISMATCH');}
 const rows=blocked?[]:check.COMPARISON_METRICS.map(([name,unit,origin])=>({
 name,unit,scenario:{origin,availability:'AVAILABLE',value:name==='frame_count'?'4':'0'},
 historical_segment:{origin,availability:'AVAILABLE',value:name==='frame_count'?'4':'0'}
 }));
 return {version:'phase165b-v1',foundation,scenario_receipt_fingerprint:sha,
 selected_segment_index:0,display_policy:blocked?'BLOCKED':'DESCRIPTIVE_ONLY',
 rows,risk_states:blocked?null:{scenario:{NORMAL:4},historical_segment:{NORMAL:4}},
 differences_available:false,cross_segment_aggregation_allowed:false,
 strategy_ranking_allowed:false,matched_market_evidence_verified:false,
 authority:'NONE',read_only:true,limitations:['no performance inference'],receipt_fingerprint:sha};
}
test('valid bounded backend receipt can be shown only descriptively',()=>{
 const r=check.checkedQuantitativeReceipt(fixture());
 assert.equal(r.foundation.classification,'CONTEXT_ONLY');
 assert.equal(r.rows.length,check.COMPARISON_METRICS.length);
 assert.equal(r.rows.find(x=>x.name==='fill_count').historical_segment.value,'0');
 assert.equal(check.metricText('1.123456789'),'1.123456…');
 assert.equal(check.metricText(null),'Unavailable');
});
test('different markets remain blocked, no metric rows',()=>{
 const r=check.checkedQuantitativeReceipt(fixture(true));
 assert.equal(r.display_policy,'BLOCKED');assert.equal(r.rows.length,0);
});
test('cannot claim alignment, live authority, deltas or strategies ranked',()=>{
 for(const [key,value] of [['authority','TRADE'],['differences_available',true],
 ['cross_segment_aggregation_allowed',true],['strategy_ranking_allowed',true],
 ['matched_market_evidence_verified',true]]){
 const r=fixture();r[key]=value;
 assert.throws(()=>check.checkedQuantitativeReceipt(r),String(key));}
 const r=fixture();r.foundation.classification='ALIGNED';
 assert.throws(()=>check.checkedQuantitativeReceipt(r));
});
test('must match segment and reserve original/source trust flags',()=>{
 for(const mutate of [
 r=>r.selected_segment_index=1,
 r=>r.foundation.historical.source_authenticated=true,
 r=>r.foundation.historical.licensing_independently_verified=true,
 r=>r.foundation.historical.segment_index=2,
 r=>r.foundation.scenario.source_kind='RECORDED_NATIVE',
 ]){
 const r=fixture();mutate(r);assert.throws(()=>check.checkedQuantitativeReceipt(r));}
});
test('no value fabrications, float values or wrong units/origins',()=>{
 for(const mutate of [
 r=>r.rows[2].scenario.value=1.125,
 r=>r.rows[2].scenario.value='NaN',
 r=>r.rows[2].scenario.value='1e8',
 r=>r.rows[2].scenario.availability='NOT_REPORTED',
 r=>r.rows[2].scenario.origin='PAPER_VAULT',
 r=>r.rows[2].unit='base',
 r=>r.rows.shift(),
 r=>r.rows[0].historical_segment.value='999',
 r=>r.risk_states.historical_segment.NORMAL=5,
 ]){
 const r=fixture();mutate(r);assert.throws(()=>check.checkedQuantitativeReceipt(r));}
 const r=fixture();r.rows[2].scenario.value=null;
 r.rows[2].scenario.availability='NOT_REPORTED';
 assert.equal(check.checkedQuantitativeReceipt(r).rows[2].scenario.value,null);
});
test('parse limits and rejects malicious or malformed payloads',()=>{
 assert.equal(check.parseComparisonReceipt(JSON.stringify(fixture())).version,'phase165b-v1');
 assert.throws(()=>check.parseComparisonReceipt('{'));
 assert.throws(()=>check.parseComparisonReceipt('x'.repeat(260000)),/256 KB/);
});
test('trace slots require original matching run and replay source identities',()=>{
 const r=fixture();
 const evidence={scenario:{simulated:true,run_fingerprint:sha,dataset_fingerprint:sha,engine_version:'phase10'},
 historical:{result_fingerprint:sha,request:{dataset_fingerprint:sha},
 segments:[{run_fingerprint:sha,dataset_fingerprint:sha,simulation_result_fingerprint:sha}]}};
 assert.equal(check.attachedTraceMatches(r,evidence),true);
 evidence.historical.segments[0].run_fingerprint='b'.repeat(64);
 assert.equal(check.attachedTraceMatches(r,evidence),false);
});
test('same-millisecond microsecond observations are not discarded',()=>{
 const r=fixture();assert.equal(check.checkedQuantitativeReceipt(r).foundation.scenario.window_status,'TRACE_COMPLETE');
});
