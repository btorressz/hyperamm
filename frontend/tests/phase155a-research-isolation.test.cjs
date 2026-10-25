const {test}=require('node:test'),assert=require('node:assert/strict');
const {load,fixture,simulation,boundary}=require('./phase154-test-helpers.cjs');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const s=load('stores/marketResearchComparison.js').useMarketResearchComparisonStore;
const live=load('stores/liveMarkets.js').useLiveMarketStore;
test('BTC/ETH/SOL research retention, selection and retirement preserve observed market authority and original results',()=>{
 const before=structuredClone({...live.getState(),selectMarket:undefined,retire:undefined,acceptSnapshot:undefined,acceptFrame:undefined,rejectFrame:undefined});
 s.setState({results:[],selectedId:'',artifact:null});
 for(const m of ['BTC','ETH','SOL']){
  const f=fixture(m),result=simulation(f.request),original=structuredClone(result);s.getState().retain(result);s.getState().select(result.run_fingerprint);
  s.getState().freeze({data:f.response,boundary:boundary(f.request,f.response),receivedAt:1,historicalReason:null});
  s.getState().retire('offline');s.getState().retire('fresh update');assert.equal(s.getState().artifact.historicalReason,'offline');assert.deepEqual(result,original);
 }
 assert.deepEqual({...live.getState(),selectMarket:undefined,retire:undefined,acceptSnapshot:undefined,acceptFrame:undefined,rejectFrame:undefined},before);
});
test('invalid result replacement is atomic and cannot remove the prior valid result or historical artifact',()=>{
 const before=s.getState(),result=simulation(fixture().request);result.simulated=false;
 assert.throws(()=>s.getState().retain(result));assert.equal(s.getState(),before);
});
test('confidence and performance retain partial, missing and unauthenticated PAPER limitations',()=>{
 const d=fixture().response;
 const html=renderToStaticMarkup(React.createElement(load('components/research-comparison/ComparisonConfidence.js').ComparisonConfidence,{data:d}));
 assert.match(html,/Partially comparable/);assert.match(html,/Missing \/ incomparable/);assert.match(html,/not authenticated server execution/);
 const performance=renderToStaticMarkup(React.createElement(load('components/research-comparison/ComparisonPerformanceContext.js').ComparisonPerformanceContext,{research:d.research}));
 assert.match(performance,/client-supplied PAPER/);assert.match(performance,/Hypothetical session PnL/);
});
test('evicting a selected research result clears the selection without relabeling a retained artifact',()=>{
 s.setState({results:[],selectedId:'',artifact:null});
 const f=fixture(),first=simulation(f.request);s.getState().retain(first);s.getState().select(first.run_fingerprint);
 for(const digit of ['b','c','d']){const next=structuredClone(first);next.run_fingerprint=digit.repeat(64);s.getState().retain(next);}
 assert.equal(s.getState().selectedId,'');assert.equal(s.getState().results.length,3);
});
