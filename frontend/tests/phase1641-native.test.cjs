const {test}=require('node:test'),assert=require('node:assert/strict');
const path=require('node:path');
const load=n=>require(path.join(process.env.TERMINAL_TEST_BUILD,n));
const r=load('utils/replayEvidence.js');
const native=require('./fixtures/phase1641-native.json');
for(const c of native.cases){
 test(`${c.summary.market}: actual serialized Pydantic receipts bind source and independent segment archives`,()=>{
  assert.deepEqual(r.checkedReplaySummaries([c.summary]),[c.summary]);
  assert.equal(r.checkedReplayProvenance(c.provenance,c.summary),c.provenance);
  assert.equal(r.checkedReplayResult(c.result,c.result.request),c.result);
  for(const s of c.result.segments){
   assert.notEqual(s.dataset_fingerprint,c.summary.dataset_fingerprint);
   const model=r.readSegmentArchive(s),base=r.readSegmentArchive(s,true);
   assert.equal(model.run_fingerprint,s.run_fingerprint);
   assert.notEqual(model.run_fingerprint,base.run_fingerprint);
   assert.equal(model.metrics.session_pnl,s.session_pnl);
   assert.equal(model.metrics.fill_count,0);
   assert.equal(model.metrics.mean_mature_markout_bps,null);
  }
 });
}
const fixture=()=>structuredClone(native.cases[0]);
for(const [label,mutate] of [
 ['wrong run',s=>s.run_fingerprint='b'.repeat(64)],
 ['source fingerprint substituted for segment',s=>s.dataset_fingerprint=native.cases[0].summary.dataset_fingerprint],
 ['another segment archive',s=>s.simulation_result_json=native.cases[0].result.segments[1].simulation_result_json],
 ['missing metrics',s=>{const a=JSON.parse(s.simulation_result_json);a.metrics={};s.simulation_result_json=JSON.stringify(a)}],
 ['nondecimal metric',s=>{const a=JSON.parse(s.simulation_result_json);a.metrics.session_pnl=1;s.simulation_result_json=JSON.stringify(a)}],
 ['fabricated trace',s=>{const a=JSON.parse(s.simulation_result_json);a.trace[0].sequence=999;s.simulation_result_json=JSON.stringify(a)}],
 ['baseline replaced by model',s=>s.baseline_result_json=s.simulation_result_json],
 ['oversized baseline',s=>s.baseline_result_json=' '.repeat(16000001)],
]) test(`selected archives reject ${label}`,()=>{
 const {result}=fixture(),s=result.segments[0];mutate(s);
 assert.throws(()=>r.readSegmentArchive(s,label.startsWith('baseline')||label==='oversized baseline'));
});
for(const [label,mutate] of [
 ['wrong settings',x=>x.request.execution.size_decimals=3],
 ['wrong frame count',x=>x.frame_count++],
 ['malformed fingerprint',x=>x.segments[0].dataset_fingerprint='z'.repeat(64)],
 ['missing baseline',x=>x.segments[0].baseline_result_json=null],
 ['wrong source label',x=>x.segments[0].frames[0].economics='SYNTHETIC_FIXTURE_VALUES'],
 ['empty book',x=>x.segments[0].frames[0].book_observation.order_book.bids=[]],
 ['future receipt',x=>x.segments[0].frames[0].book_observation.received_at='2099-01-01T00:00:00Z'],
 ['provider event time on context',x=>x.segments[0].frames[0].context_observation.source_timestamp='2026-01-01T00:00:00Z'],
 ['malformed issues',x=>x.issues=[{code:{private:'payload'}}]],
 ['oversized gap list',x=>x.declared_gaps=Array(1025).fill(x.declared_gaps[0])],
 ['unsafe controls',x=>x.request.execution.paper.depth_sensitive='true'],
]) test(`receipt rejects ${label}`,()=>{
 const {result}=fixture(),request=structuredClone(result.request);mutate(result);
 assert.throws(()=>r.checkedReplayResult(result,request));
});
test('unselected archives stay lazy and financial deltas remain server values',()=>{
 const {result}=fixture();result.segments[1].simulation_result_json='{';
 assert.equal(r.checkedReplayResult(result,result.request),result);
 assert.equal(r.readSegmentArchive(result.segments[0]).metrics.session_pnl,result.segments[0].session_pnl);
 assert.throws(()=>r.readSegmentArchive(result.segments[1]));
});
test('streamed historical JSON enforces byte budget before parsing',async()=>{
 const {readHistoricalJson}=load('api/client.js');
 assert.deepEqual(await readHistoricalJson(new Response('{"ok":true}'),32),{ok:true});
 await assert.rejects(readHistoricalJson(new Response(' '.repeat(33)),32),/budget/);
 await assert.rejects(readHistoricalJson(new Response('{}',{headers:{'Content-Length':'33'}}),32),/budget/);
 await assert.rejects(readHistoricalJson(new Response('{')),/malformed/);
});
test('HTTP 422 banners admit only fixed contract labels, never raw provider or path data',async()=>{
 const {api}=load('api/client.js'),old=global.fetch;
 try{
  global.fetch=async()=>new Response(JSON.stringify({detail:{issues:[{code:'/private/secret',missing_fields:['token=secret','mark_price']},null]}}),{status:422});
  await assert.rejects(api.historicalReplayRun({}),e=>!/private|secret|token=/.test(e.message)&&e.message.includes('mark_price'));
 }finally{global.fetch=old;}
});
test('native microsecond receipts stay distinct inside one display millisecond',()=>{
 const c=native.cases.find(c=>c.summary.market==='ETH');
 assert.equal(Date.parse(c.summary.coverage_start),Date.parse(c.summary.coverage_end));
 assert.equal(r.checkedReplayResult(c.result,c.result.request).frame_count,4);
 assert.deepEqual(c.result.segments[0].frames.map(f=>f.sequence),[2,4,6,8]);
 assert.equal(r.readSegmentArchive(c.result.segments[0]).trace.length,4);
});
test('captured configuration rejects malformed JSON or execution authority',()=>{
 for(const wire of ['{','{}',JSON.stringify({strategy:{market:'BTC',execution_mode:'TESTNET'},risk:{},agents:{},simulation:{},market_profile:{}})]){
  const {result}=fixture();result.captured_configuration_json=wire;
  assert.throws(()=>r.checkedReplayResult(result,result.request));
 }
});
test('large chart tables are bounded while chart coordinates retain every sequence',()=>{
 const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
 const {HistoryChart,seriesCoordinates}=load('components/HistoryChart.js');
 const points=Array.from({length:5000},(_,i)=>({sequence:i,timestamp:'2026-01-01T00:00:00Z',mid:'1'}));
 const lines=[{key:'mid',label:'Mid',color:'#fff'}];
 const html=renderToStaticMarkup(React.createElement(HistoryChart,{points,lines,axis:'frame'}));
 assert.equal((html.match(/<tr>/g)||[]).length,201);
 assert.match(html,/first 200 of 5000/);
 assert.equal(seriesCoordinates(points,lines[0],'frame').length,5000);
});
