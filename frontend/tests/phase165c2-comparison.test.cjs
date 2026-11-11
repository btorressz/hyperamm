const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const check=require(path.join(process.env.TERMINAL_TEST_BUILD,'utils/scenarioReplayComparison.js'));
const client=require(path.join(process.env.TERMINAL_TEST_BUILD,'api/client.js'));
const fixture=require('./fixtures/phase165c2-response.json');
const clone=()=>structuredClone(fixture);
test('actual server-generated BTC receipt and original bounded traces parse',()=>{
 const r=check.checkedComparisonResponse(clone(),fixture.request);
 assert.equal(r.receipt.foundation.classification,'CONTEXT_ONLY');
 assert.equal(r.scenario_trace.points.length,4);assert.equal(r.historical_trace.source_times.length,4);
 assert.equal(r.receipt.rows.find(x=>x.name==='fill_count').historical_segment.value,'0');
 assert.equal(r.receipt.rows.find(x=>x.name==='fill_activity_ratio').historical_segment.value,null);
});
test('reject stale dataset, market, frame, execution, segment and source identities',()=>{
 for(const mutate of [
 r=>r.request.frames=5,r=>r.request.research_market='SOL',r=>r.request.historical.execution.size_decimals=2,
 r=>r.request.historical.dataset_fingerprint='b'.repeat(64),r=>r.receipt.selected_segment_index=1,
 r=>r.historical_trace.run_fingerprint='b'.repeat(64),r=>r.historical_trace.dataset_fingerprint='b'.repeat(64),
 r=>r.segments[0].simulation_result_fingerprint='b'.repeat(64),r=>r.provenance.source_authenticated=true,
 r=>r.receipt.foundation.classification='ALIGNED',r=>r.receipt.differences_available=true,
 r=>r.scenario_trace.points.push(r.scenario_trace.points[0]),r=>r.scenario_trace.points[1].sequence=0,
 r=>r.historical_trace.source_times.pop(),r=>r.scenario_trace.points[0].equity=42,
 r=>r.scenario_trace.points[0].timestamp='invalid',r=>r.scenario_trace.omitted_points=99,
 ]){const r=clone();mutate(r);assert.throws(()=>check.checkedComparisonResponse(r,fixture.request));}
});
test('streaming response budget rejects declared and chunked oversized bodies',async()=>{
 await assert.rejects(()=>client.readHistoricalJson(new Response('x',{headers:{'Content-Length':'1000001'}}),1000000));
 const chunk=new Uint8Array(600000);const stream=new ReadableStream({start(c){c.enqueue(chunk);c.enqueue(chunk);c.close()}});
 await assert.rejects(()=>client.readHistoricalJson(new Response(stream),1000000));
 await assert.rejects(()=>client.readHistoricalJson(new Response('{'),1000000));
});
test('typed API sends captured request, no-store and AbortSignal; strict receipt parsing',async()=>{
 const old=global.fetch,controller=new AbortController();
 global.fetch=async(url,init)=>{
 assert.equal(url,'/api/v1/research-comparison/scenario-historical');assert.equal(init.cache,'no-store');
 assert.equal(init.signal,controller.signal);assert.deepEqual(JSON.parse(init.body),fixture.request);
 return new Response(JSON.stringify(fixture),{headers:{'Content-Type':'application/json'}});
 };
 try{assert.equal((await client.api.scenarioHistoricalComparison(fixture.request,controller.signal)).version,'phase165c2-v1')}
 finally{global.fetch=old}
});
test('busy/unavailable/invalid/internal errors remain bounded public messages',async()=>{
 const old=global.fetch;
 try{for(const status of [422,429,503,500]){
 global.fetch=async()=>new Response('{}',{status});
 await assert.rejects(()=>client.api.scenarioHistoricalComparison(fixture.request),new RegExp(String(status===429?'busy':status===503?'unavailable':status)));
 }}finally{global.fetch=old}
});
