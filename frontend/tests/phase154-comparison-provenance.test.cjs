const {test}=require('node:test'),assert=require('node:assert/strict');
const {load,fixture,boundary}=require('./phase154-test-helpers.cjs');
const u=load('utils/marketResearchComparison.js');
for(const field of ['market','liveSelection','liveBoundary','observer','generation','researchRun','researchDataset','researchProfile','researchVersion','researchEpoch','requestGeneration'])test(`completion retired after ${field} changes`,()=>{
 const f=fixture(),a=boundary(f.request,f.response),b={...a,[field]:typeof a[field]==='number'?a[field]+1:'changed'};assert.equal(u.sameBoundary(a,b),false);
});
for(const field of ['observer_instance_id','connection_generation','l2_source_timestamp','perp_observed_at','research_frame_timestamp','research_trust'])test(`wrong response provenance ${field} rejected`,()=>{
 const f=fixture(),b=boundary(f.request,f.response);f.response.provenance[field]=field==='connection_generation'?99:'wrong';assert.throws(()=>u.checkedMarketComparison(f.response,f.request,b));
});
for(const kind of ['nonfinite','delta','duplicate','version','research','completeness'])test(`malformed comparison ${kind} rejected`,()=>{
 const f=fixture(),b=boundary(f.request,f.response);
 if(kind==='nonfinite')f.response.metrics[0].absolute_difference='Infinity';
 if(kind==='delta'){f.response.metrics[0].comparison_status='UNAVAILABLE';f.response.metrics[0].absolute_difference='1';}
 if(kind==='duplicate')f.response.metrics[1]=f.response.metrics[0];
 if(kind==='version')f.response.contract_version='future';
 if(kind==='research')f.response.research.run_fingerprint='f'.repeat(64);
 if(kind==='completeness')f.response.explainability.available_metrics=[];
 assert.throws(()=>u.checkedMarketComparison(f.response,f.request,b));
});
test('cross-asset delta is rejected by client boundary',()=>{
 const f=fixture(),b=boundary(f.request,f.response);f.request.market='ETH';b.market='ETH';assert.throws(()=>u.checkedMarketComparison(f.response,f.request,b));
});
