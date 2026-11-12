const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const u=require(path.join(process.env.TERMINAL_TEST_BUILD,'utils/researchStatus.js'));

for(const method of ['runSimulation','optimizeSimulation','researchPreview','compareResearch']){
 test('Scenario and Vault '+method+' error bodies cannot expose private diagnostics',async()=>{
  const http=require('node:http'),{once}=require('node:events');
  const {api}=require(path.join(process.env.TERMINAL_TEST_BUILD,'api/client.js'));
  let status=422;
  const server=http.createServer((req,res)=>{
   req.resume();res.writeHead(status,{'Content-Type':'application/json'});
   res.end(JSON.stringify({detail:status===422?
    [{loc:['body','/private/acceptance-path'],msg:'Traceback API_KEY=synthetic-secret'}]:
    'Traceback /private/acceptance-path API_KEY=synthetic-secret'}));
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  const original=global.fetch;
  global.fetch=(url,init)=>original(new URL(url,'http://127.0.0.1:'+server.address().port),init);
  try{
   for(const [code,kind] of [[413,'size'],[422,'validation'],[429,'busy'],[500,'server'],[503,'storage']]){
    status=code;
    await assert.rejects(()=>api[method]({}),error=>{
     assert.doesNotMatch(error.message,/Traceback|\/private\/|API_KEY|synthetic-secret/);
     assert.equal(u.diagnoseResearchError(error).kind,kind);
     return true;
    });
   }
  }finally{global.fetch=original;await new Promise(resolve=>server.close(resolve))}
 });
}

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

test('workload accepts all research markets, source assertions, execution models and independent frame edits',()=>{
 for(const market of ['BTC','ETH','SOL'])for(const source_kind of ['SYNTHETIC_FIXTURE','RECORDED_NATIVE'])for(const executionMode of ['BASELINE','MODELED_CROSSING']){
  const w=u.researchWorkload({dataset:{...dataset,market,source_kind},replayFrames:'4999',scenarioFrames:'2',executionMode});
  assert.equal(w.fields.find(x=>x.label==='Research market').value,market+'-PERP');
  assert.equal(w.fields.find(x=>x.label==='Source label').value,source_kind==='RECORDED_NATIVE'?'User-asserted recording':'Synthetic fixture');
  assert.equal(w.fields.find(x=>x.label==='Scenario frame limit').value,'2 of 5,000 maximum');
  assert.equal(w.large,true);
 }
 assert.equal(u.researchWorkload({dataset,replayFrames:'2',scenarioFrames:'1000',executionMode:'BASELINE'}).large,true);
});

test('shared status and diagnostics expose accessible roles and bounded messages',()=>{
 const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
 const {ResearchRunStatus}=require(path.join(process.env.TERMINAL_TEST_BUILD,'components/research/ResearchRunStatus.js'));
 const {ResearchDiagnostics}=require(path.join(process.env.TERMINAL_TEST_BUILD,'components/research/ResearchDiagnostics.js'));
 assert.equal(renderToStaticMarkup(React.createElement(ResearchRunStatus,{state:'idle',operation:'Historical replay'})),'');
 for(const state of ['running','complete','retired','error']){
  const html=renderToStaticMarkup(React.createElement(ResearchRunStatus,{state,operation:'Historical replay'}));
  assert.match(html,/role="status"/);assert.match(html,/aria-live="polite"/);
  assert.doesNotMatch(html,/\d+%|worker running|cancellation successful/i);
 }
 const html=renderToStaticMarkup(React.createElement(ResearchDiagnostics,{error:new Error('HTTP 500 /private/path token=unsafe')}));
 assert.match(html,/role="alert"/);assert.doesNotMatch(html,/unsafe|\/private\/path/);
});

test('real HTTP status responses through the actual API client produce safe shared guidance',async()=>{
 const http=require('node:http'),{once}=require('node:events');
 const {api}=require(path.join(process.env.TERMINAL_TEST_BUILD,'api/client.js'));
 const fixture=require('./fixtures/phase165c2-response.json');
 let status=200;
 const server=http.createServer((req,res)=>{
  req.resume();res.writeHead(typeof status==='number'?status:200,{'Content-Type':'application/json'});
  if(status==='disconnect'){res.flushHeaders();res.write('{');setTimeout(()=>res.destroy(),20);return;}
  if(status==='malformed'){res.end('{');return;}
  if(status==='invalid-utf8'){res.end(Buffer.from([255]));return;}
  res.end(JSON.stringify(status===200?fixture:{detail:'Traceback /private/path API_KEY=unsafe'}));
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');
 const original=global.fetch;
 global.fetch=(url,init)=>original(new URL(url,'http://127.0.0.1:'+server.address().port),init);
 try{
  assert.equal((await api.scenarioHistoricalComparison(fixture.request)).receipt.foundation.classification,'CONTEXT_ONLY');
  status='disconnect';
  await assert.rejects(()=>api.scenarioHistoricalComparison(fixture.request),error=>{
   assert.equal(u.diagnoseResearchError(error).kind,'connection');return true;
  });
  for(const invalid of ['malformed','invalid-utf8']){
   status=invalid;
   await assert.rejects(()=>api.scenarioHistoricalComparison(fixture.request),error=>{
    assert.equal(u.diagnoseResearchError(error).kind,'validation');return true;
   });
  }
  for(const [code,kind] of [[413,'size'],[422,'validation'],[429,'busy'],[503,'storage'],[500,'server']]){
   status=code;
   await assert.rejects(()=>api.scenarioHistoricalComparison(fixture.request),error=>{
    assert.equal(u.diagnoseResearchError(error).kind,kind);
    assert.doesNotMatch(error.message,/unsafe|private\/path|Traceback/);return true;
   });
  }
 }finally{global.fetch=original;await new Promise(resolve=>server.close(resolve))}
});
