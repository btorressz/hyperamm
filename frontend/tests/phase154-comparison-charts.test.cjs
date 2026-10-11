const {test}=require('node:test'),assert=require('node:assert/strict');
const {load,fixture}=require('./phase154-test-helpers.cjs');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const u=load('utils/marketResearchComparison.js');
test('paired evidence has independent actual timestamps, no invented common axis',()=>{
 const f=fixture(),p=u.pairedPriceEvidence(f.response);assert.equal(p.observed.time,f.response.provenance.l2_source_timestamp);assert.equal(p.research.time,f.response.provenance.research_frame_timestamp);assert.notEqual(p.observed.time,p.research.time);
 const html=renderToStaticMarkup(React.createElement(load('components/research-comparison/ComparisonPriceChart.js').ComparisonPriceChart,{data:f.response}));assert.match(html,/two independent contexts/);assert.match(html,/not simultaneous market ticks/);assert.doesNotMatch(html,/canvas|candlestick|OHLC/);
});
test('missing observed midpoint remains unavailable',()=>{
 const f=fixture();f.response.metrics.find(x=>x.metric_name==='midpoint').observed_value=null;assert.equal(u.pairedPriceEvidence(f.response).observed.value,null);
});
test('financial table retains exact values, units, reason and accessible headings',()=>{
 const f=fixture();f.response.metrics[0].observed_value='9007199254740993.123456789';
 const html=renderToStaticMarkup(React.createElement(load('components/research-comparison/ComparisonMetricTable.js').ComparisonMetricTable,{metrics:f.response.metrics,title:'Evidence'}));
 assert.match(html,/9007199254740993.123456789/);assert.match(html,/scope="col"/);assert.match(html,/Observed market/);assert.match(html,/Hypothetical research/);assert.match(html,/raw rate/);assert.match(html,/basis points/);assert.match(html,/base/);
});
test('performance, accounting legacy limitation and no live profit claim',()=>{
 const f=fixture();const html=renderToStaticMarkup(React.createElement(load('components/research-comparison/ComparisonPerformanceContext.js').ComparisonPerformanceContext,{research:f.request.research}));
 assert.match(html,/Hypothetical session PnL/);assert.match(html,/observed snapshot did not generate/);assert.match(html,/provenance unavailable/);assert.doesNotMatch(html,/actual live PnL|expected return/i);
});
test('confidence explains descriptive trust, not profitability',()=>{
 const f=fixture();const html=renderToStaticMarkup(React.createElement(load('components/research-comparison/ComparisonConfidence.js').ComparisonConfidence,{data:f.response}));
 assert.match(html,/CROSS_CONTEXT_DESCRIPTIVE_ONLY/);assert.match(html,/not independently authenticated/);assert.match(html,/does not predict strategy profitability/);
});
