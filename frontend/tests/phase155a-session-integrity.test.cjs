const {test}=require('node:test'),assert=require('node:assert/strict');
const {load,fixture,boundary}=require('./phase154-test-helpers.cjs');
const {ComparisonRequestGate}=load('utils/marketResearchComparison.js');
const s=load('stores/marketResearchComparison.js').useMarketResearchComparisonStore;
test('old response arriving after a newer capture cannot replace the new artifact',async()=>{
 const f=fixture(),b=boundary(f.request,f.response),gate=new ComparisonRequestGate();
 s.setState({artifact:null});
 let release;const delayed=new Promise(r=>release=r),old=gate.begin();
 const pending=delayed.then(()=>{if(gate.accepts(old,b,b))s.getState().freeze({data:f.response,boundary:b,receivedAt:1,historicalReason:null});});
 const latest=gate.begin();assert.equal(old.signal.aborted,true);
 if(gate.accepts(latest,b,b))s.getState().freeze({data:f.response,boundary:b,receivedAt:2,historicalReason:null});
 release();await pending;assert.equal(s.getState().artifact.receivedAt,2);
});
for(const event of ['unmount','disconnect','reconnect','result replacement','workspace exit'])test(`${event} permanently invalidates the pending ticket`,()=>{
 const f=fixture(),b=boundary(f.request,f.response),gate=new ComparisonRequestGate(),ticket=gate.begin();
 gate.retire();assert.equal(gate.accepts(ticket,b,b),false);assert.equal(ticket.signal.aborted,true);
 const next=gate.begin();assert.equal(gate.accepts(ticket,b,b),false);assert.equal(gate.accepts(next,b,b),true);
});
for(const key of ['market','researchRun','researchDataset','researchProfile','researchVersion','researchEpoch','liveBoundary','observer','generation','liveSelection'])test(`pending response rejected across ${key} boundary`,()=>{
 const f=fixture(),b=boundary(f.request,f.response),gate=new ComparisonRequestGate(),ticket=gate.begin();
 const changed={...b,[key]:typeof b[key]==='number'?b[key]+1:'changed'};
 assert.equal(gate.accepts(ticket,b,changed),false);assert.equal(gate.accepts(ticket,b,null),false);
});
