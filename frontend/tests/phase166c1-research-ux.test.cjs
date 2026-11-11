const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const u=require(path.join(process.env.TERMINAL_TEST_BUILD,'utils/researchStatus.js'));

const dataset={
  contract_version:'phase16-replay-v1',dataset_id:'fixture',dataset_fingerprint:'a'.repeat(64),
  market:'BTC',source_kind:'SYNTHETIC_FIXTURE',coverage_start:'2026-11-01T00:00:00Z',
  coverage_end:'2026-11-01T00:10:00Z',coverage_status:'PARTIAL',observation_count:3200,
  gap_count:2,source_authenticated:false,licensing_independently_verified:false,
  continuous_history_verified:false,read_only:true,authority:'NONE',
};
test('preflight derives bounded source metadata, never predicted successful frames or elapsed time',()=>{
 const plan=u.researchWorkload({
   dataset,replayFrames:'4999',scenarioFrames:'5000',executionMode:'MODELED_CROSSING'});
 assert.equal(plan.valid,true);
 assert.equal(plan.large,true);
 assert.deepEqual(plan.fields.find(x=>x.label==='Research market'),{label:'Research market',value:'BTC-PERP'});
 assert.equal(plan.fields.find(x=>x.label==='Admitted observations').value,'3200');
 assert.equal(plan.fields.find(x=>x.label==='Declared gaps').value,'2');
 assert.equal(plan.fields.find(x=>x.label==='Scenario frame limit').value,'5000 of 5,000 maximum');
 assert.equal(plan.fields.find(x=>x.label==='PAPER execution').value,'Modeled crossing sensitivity');
 assert.ok(plan.notes.some(x=>x.includes('No percentage or ETA')));
 assert.ok(plan.notes.some(x=>x.includes('independent historical segment')));
 assert.ok(!JSON.stringify(plan).match(/estimated_seconds|progress_percent|predicted_fills/i));
 assert.equal(dataset.observation_count,3200);
});
test('preflight validates strict 2..5000 frame ceilings without inferring viable observations',()=>{
 for(const n of ['','-1','1','5001','2.1',' 5','2e2','NaN']){
   const w=u.researchWorkload({dataset,replayFrames:n,executionMode:'BASELINE'});
   assert.equal(w.valid,false,n);
   assert.equal(w.fields.find(x=>x.label==='Historical frame limit').value,'Invalid frame limit');
 }
 for(const n of ['2','128','999','1000','5000']){
   const w=u.researchWorkload({dataset,replayFrames:n,executionMode:'BASELINE'});
   assert.equal(w.valid,true,n);
   assert.equal(w.large,Number(n)>=1000,n);
 }
 const mismatch=u.researchWorkload({dataset,replayFrames:'128',scenarioFrames:'5001',executionMode:'BASELINE'});
 assert.equal(mismatch.valid,false);
 assert.equal(mismatch.large,false);
});
test('missing dataset never creates a synthetic source identity',()=>{
 const w=u.researchWorkload({dataset:null,replayFrames:'250',executionMode:'BASELINE'});
 assert.equal(w.valid,true);
 assert.equal(w.fields[0].value,'No admitted dataset selected');
 assert.ok(!w.fields.some(x=>x.label==='Admitted observations'));
});
test('unknown coverage and declared gap messaging remain explicit',()=>{
 const w=u.researchWorkload({dataset:{...dataset,coverage_status:'UNKNOWN',gap_count:0},
   replayFrames:'250',executionMode:'BASELINE'});
 assert.ok(w.notes.some(x=>x.includes('Coverage remains unknown')));
 assert.ok(!w.notes.some(x=>x.includes('Declared gaps may')));
});
test('research failure diagnostics distinguish the existing HTTP boundaries',()=>{
 const pairs=[
  ['Shared research worker busy. Retry after its current job completes','busy'],
  ['Research capacity is busy','busy'],
  ['Historical response exceeds the browser evidence budget.','size'],
  ['HTTP 413','size'],
  ['Historical replay vault or research admission unavailable.','storage'],
  ['HTTP 503','storage'],
  ['Historical evidence or replay settings rejected (422).','validation'],
  ['Historical provenance does not match selected dataset.','validation'],
  ['Backend connection unavailable.','connection'],
  ['Failed to fetch','connection'],
  ['Retired result after session change.','stale'],
  ['HTTP 500','server'],
  ['an unrecognized error','unknown'],
 ];
 for(const [message,kind] of pairs){
   const result=u.diagnoseResearchError(new Error(message));
   assert.equal(result.kind,kind,message);
   assert.ok(result.title.length>0&&result.action.length>20);
   assert.ok(!result.action.includes(message));
 }
});
test('diagnostics never echo untrusted provider credentials or raw traceback text',()=>{
 const secret='secret-provider-token';
 const d=u.diagnoseResearchError('Traceback API_KEY='+secret+'; upstream died');
 assert.ok(!JSON.stringify(d).includes(secret));
 const undef=u.diagnoseResearchError({stack:'internal private path '+secret});
 assert.equal(undef.kind,'unknown');
 assert.ok(!JSON.stringify(undef).includes(secret));
});
