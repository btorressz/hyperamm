const {test}=require('node:test'),assert=require('node:assert/strict');
const {load,fixture,boundary}=require('./phase154-test-helpers.cjs');
const u=load('utils/marketResearchComparison.js');
for(const key of ['session_pnl','quoted_notional','risk_halt_fraction','mean_mature_markout_bps'])test(`missing required PAPER metric ${key} rejected`,()=>{
 const f=fixture();delete f.request.research.performance[key];assert.throws(()=>u.checkedResearchSummary(f.request.research));
});
for(const key of ['observed_value','research_assumed_value'])test(`metric ${key} cannot contradict its attributed source`,()=>{
 const f=fixture();f.response.metrics[0][key]='123456.789';assert.throws(()=>u.checkedMarketComparison(f.response,f.request,boundary(f.request,f.response)));
});
test('completeness partitions must correspond to the actual comparable rows',()=>{
 const f=fixture(),e=f.response.explainability;
 [e.available_metrics[0],e.missing_metrics[0]]=[e.missing_metrics[0],e.available_metrics[0]];
 assert.throws(()=>u.checkedMarketComparison(f.response,f.request,boundary(f.request,f.response)));
});
test('valid large relative differences are not confused with bounded input values',()=>{
 const f=fixture();f.response.metrics[0].difference_bps='10000000000000000000000000000000000000000';
 assert.equal(u.checkedMarketComparison(f.response,f.request,boundary(f.request,f.response)),f.response);
});
for(const bad of ['NaN','Infinity','1e9999',true,'x'.repeat(257)])test(`invalid output difference ${String(bad).slice(0,12)}`,()=>{
 const f=fixture();f.response.metrics[0].difference_bps=bad;assert.throws(()=>u.checkedMarketComparison(f.response,f.request,boundary(f.request,f.response)));
});
