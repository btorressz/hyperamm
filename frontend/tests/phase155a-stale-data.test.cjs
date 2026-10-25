const {test}=require('node:test'),assert=require('node:assert/strict');
const {load,fixture}=require('./phase154-test-helpers.cjs');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const u=load('utils/marketResearchComparison.js');
const fresh=load('utils/liveMarketEvidence.js').liveFreshness;
for(const component of ['book','context']) {
 test(`${component}: eligibility, independent stale state, missing and historical labels`,()=>{
  const d=fixture().response,field=component==='book'?'l2':'perp';
  assert.equal(u.capturedEvidenceLabel(d,component),'CURRENT / ELIGIBLE AT CAPTURE');
  d.observed.snapshot.status[field+'_freshness']='STALE';d.observed[component+'_eligible']=false;
  assert.equal(u.capturedEvidenceLabel(d,component),'STALE');
  assert.equal(u.capturedEvidenceLabel(d,component==='book'?'context':'book'),'CURRENT / ELIGIBLE AT CAPTURE');
  assert.equal(u.capturedEvidenceLabel(d,component,'source expired'),'HISTORICAL');
  d.observed.snapshot[component==='book'?'order_book':'perp_context']=null;
  assert.equal(u.capturedEvidenceLabel(d,component),'UNAVAILABLE');
 });
}
test('stale retained observed midpoint stays exact with its independent timestamp and prominent label',()=>{
 const d=fixture().response;d.observed.snapshot.status.l2_freshness='STALE';d.observed.book_eligible=false;
 const before=structuredClone(d),pair=u.pairedPriceEvidence(d);
 assert.equal(pair.observed.value,d.metrics[0].observed_value);assert.match(pair.observed.label,/STALE/);
 assert.equal(pair.observed.time,d.provenance.l2_source_timestamp);assert.deepEqual(d,before);
 const html=renderToStaticMarkup(React.createElement(load('components/research-comparison/ComparisonPriceChart.js').ComparisonPriceChart,{data:d}));
 assert.match(html,/STALE/);assert.doesNotMatch(html,/CURRENT \/ ELIGIBLE/);
});
test('historical chart and deltas cannot look current after source retirement',()=>{
 const d=fixture().response;
 const chart=renderToStaticMarkup(React.createElement(load('components/research-comparison/ComparisonPriceChart.js').ComparisonPriceChart,{data:d,historicalReason:'offline'}));
 const table=renderToStaticMarkup(React.createElement(load('components/research-comparison/ComparisonMetricTable.js').ComparisonMetricTable,{metrics:d.metrics,title:'Evidence',historicalReason:'offline'}));
 assert.match(chart,/HISTORICAL/);assert.doesNotMatch(chart,/CURRENT \/ ELIGIBLE/);assert.match(table,/HISTORICAL/);assert.match(table,/not current market evidence/);
});
test('captured age advances independently of newer snapshots and fails closed offline',()=>{
 const d=fixture().response,e={snapshot:d.observed.snapshot,receivedAt:1000,transitSeconds:0};
 assert.equal(fresh(e,1000,true).book,true);
 assert.equal(fresh(e,1000+e.snapshot.status.l2_stale_after_seconds*1000+1000,true).book,false);
 assert.equal(fresh(e,1000,false).book,false);
 const later={...e,receivedAt:100000};assert.equal(fresh(later,100000,true).book,true);
 assert.equal(fresh(e,100000,true).book,false);
});
test('captured transit is immutable across wall-clock rollback and caller object mutation',()=>{
 const d=fixture().response,s=load('stores/marketResearchComparison.js').useMarketResearchComparisonStore;
 const now=Date.now;
 try {
  Date.now=()=>Date.parse(d.observed.snapshot.status.evaluated_at)+5000;
  s.getState().freeze({data:d,boundary:{},receivedAt:1000,historicalReason:null});
  const captured=s.getState().artifact;assert.equal(captured.transitSeconds,5);
  Date.now=()=>0;d.metrics[0].observed_value='1';
  assert.notEqual(captured.data.metrics[0].observed_value,'1');
  assert.equal(fresh({snapshot:captured.data.observed.snapshot,receivedAt:1000,transitSeconds:captured.transitSeconds},8000,true).book,false);
 } finally {Date.now=now;}
});
