const {test}=require('node:test'),assert=require('node:assert/strict');
const {load,fixture,boundary,simulation}=require('./phase154-test-helpers.cjs');
const u=load('utils/marketResearchComparison.js');
for(const m of ['BTC','ETH','SOL'])test(`${m} actual completed summary and captured comparison accepted`,()=>{
 const f=fixture(m),b=boundary(f.request,f.response);
 assert.deepEqual(u.researchSummary(simulation(f.request)),f.request.research);
 assert.equal(u.checkedMarketComparison(f.response,f.request,b),f.response);
 assert.equal(f.response.research.assumptions.market,m);
});
for(const value of ['NaN','Infinity','-Infinity',true,1.2,'1e1000',{},null])test(`malformed financial input ${String(value)}`,()=>{
 const f=fixture();f.request.research.performance.session_pnl=value;assert.throws(()=>u.checkedResearchSummary(f.request.research));
});
for(const key of ['run_fingerprint','dataset_fingerprint','strategy_fingerprint'])test(`missing completed identity ${key}`,()=>{
 const f=fixture();delete f.request.research[key];assert.throws(()=>u.checkedResearchSummary(f.request.research));
});
test('old results retain performance with unavailable assumptions',()=>{
 const f=fixture();delete f.request.research.assumptions;const result=simulation(f.request);delete result.research_assumptions;
 assert.equal(u.researchSummary(result).assumptions,null);
});
test('optimizer summary is not a completed simulation',()=>assert.throws(()=>u.researchSummary({simulated:true,baseline:{},ranked_candidates:[]})));
test('no result cannot be selected',()=>{
 const s=load('stores/marketResearchComparison.js').useMarketResearchComparisonStore;s.setState({results:[],selectedId:''});assert.throws(()=>s.getState().select('invented'));
});
test('exact legacy exponent financial strings normalize without float arithmetic',()=>{
 assert.equal(u.plainFinancial('0E+5'),'0');assert.equal(u.plainFinancial('123.450e-3'),'0.123450');
 assert.equal(u.plainFinancial('9007199254740993'),'9007199254740993');
});
for(const kind of ['missing','crossed','profile','market','funding','depth'])test(`invalid assumptions ${kind}`,()=>{
 const f=fixture(),a=f.request.research.assumptions;
 if(kind==='missing')delete a.bid_levels;if(kind==='crossed')a.best_bid='100000';if(kind==='profile')a.market_profile_fingerprint='d'.repeat(64);
 if(kind==='market')a.market='ETH';if(kind==='funding')a.funding_rate='NaN';if(kind==='depth')a.bid_levels=Array(6).fill(a.bid_levels[0]);
 assert.throws(()=>u.checkedResearchSummary(f.request.research));
});
for(const component of ['l2','perp'])test(`independent stale ${component} blocks only required comparison metrics`,()=>{
 const f=fixture(),b=boundary(f.request,f.response),r=f.response;
 r.observed.snapshot.observation_status='STALE';r.observed.snapshot.status[component+'_freshness']='STALE';
 r.observed[component==='l2'?'book_eligible':'context_eligible']=false;
 const book=new Set(['midpoint','best_bid','best_ask','spread_quote','spread_bps','bid_depth_base','ask_depth_base']);
 for(const m of r.metrics)if(book.has(m.metric_name)===(component==='l2')){m.comparison_status='UNAVAILABLE';m.absolute_difference=null;m.difference_bps=null;}
 r.explainability.available_metrics=r.metrics.filter(m=>['COMPARABLE','PARTIAL'].includes(m.comparison_status)).map(m=>m.metric_name);
 r.explainability.missing_metrics=r.metrics.filter(m=>!r.explainability.available_metrics.includes(m.metric_name)).map(m=>m.metric_name);
 assert.equal(u.checkedMarketComparison(r,f.request,b),r);
 const invalid=structuredClone(r);invalid.metrics.find(m=>book.has(m.metric_name)===(component==='l2')).comparison_status='COMPARABLE';assert.throws(()=>u.checkedMarketComparison(invalid,f.request,b));
});
test('disabled native source accepts unavailable evidence and retains PAPER performance',()=>{
 const f=fixture(),r=f.response,raw=require('./phase153-fixtures.json').BTC.disabled;
 r.observed.snapshot=structuredClone(raw);r.observed.snapshot.status.evaluated_at=new Date().toISOString();
 Object.assign(r.observed,{book_eligible:false,context_eligible:false,bid_depth_base:null,ask_depth_base:null,depth_level_count:0,acquisition_gap_seconds:null});
 Object.assign(r.provenance,{observer_instance_id:raw.status.observer_instance_id,connection_generation:raw.status.connection_generation,l2_source_timestamp:null,l2_observed_at:null,perp_observed_at:null});
 for(const m of r.metrics)Object.assign(m,{observed_value:null,absolute_difference:null,difference_bps:null,comparison_status:'UNAVAILABLE'});
 r.explainability.available_metrics=[];r.explainability.missing_metrics=r.metrics.map(m=>m.metric_name);r.comparison_status='UNAVAILABLE';
 assert.equal(u.checkedMarketComparison(r,f.request,boundary(f.request,r)),r);
 assert.equal(r.research.performance.session_pnl,f.request.research.performance.session_pnl);
});
