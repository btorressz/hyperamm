const {test}=require('node:test'),assert=require('node:assert/strict');
const path=require('node:path');
const r=require(path.join(process.env.TERMINAL_TEST_BUILD,'utils/replayEvidence.js'));
const sha='a'.repeat(64);
function summary(id='btc-replay'){return {contract_version:'phase16-replay-v1',
 dataset_id:id,dataset_fingerprint:sha,market:'BTC',source_kind:'RECORDED_NATIVE',
 coverage_start:'2026-01-01T00:00:00Z',coverage_end:'2026-01-01T00:00:01Z',
 coverage_status:'PARTIAL',observation_count:4,gap_count:0,source_authenticated:false,
 licensing_independently_verified:false,continuous_history_verified:false,read_only:true,authority:'NONE'};}
test('catalog accepts bounded IDs without promoting source authority',()=>{
 assert.equal(r.checkedReplaySummaries([summary()])[0].authority,'NONE');
 assert.throws(()=>r.checkedReplaySummaries([summary(),summary()]));
 for(const [key,value] of [['market','DOGE'],['authority','TRADE'],['source_authenticated',true],
  ['dataset_fingerprint','broken'],['coverage_end','2025-01-01T00:00:00Z']]){
  const x=summary();x[key]=value;assert.throws(()=>r.checkedReplaySummaries([x]),key);
 }
});
test('provenance must bind current dataset',()=>{
 const source={dataset_fingerprint:sha,source_kind:'RECORDED_NATIVE',
  authority:'NONE',read_only:true,source_authenticated:false,licensing_independently_verified:false,
  observation_count:4,limitations:[]};
 assert.equal(r.checkedReplayProvenance(source,summary()).authority,'NONE');
 assert.throws(()=>r.checkedReplayProvenance({...source,dataset_fingerprint:'b'.repeat(64)},summary()));
});
test('model inputs have strict bounds and defaults',()=>{
 const p=r.researchPaperDefaults();assert.equal(r.paperInputError(p),null);
 assert.equal(r.paperInputError({...p,slippage_bps:'2'}).includes('Baseline'),true);
 assert.equal(r.paperInputError({...p,mode:'MODELED_CROSSING',slippage_bps:'2'}),null);
 for(const v of ['NaN','1e3','-1','1001','0.1234567890123456789'])assert.ok(r.paperInputError({...p,mode:'MODELED_CROSSING',slippage_bps:v}));
 assert.ok(r.paperInputError({...p,mode:'MODELED_CROSSING',order_latency_ms:60001}));
});
test('rejects mismatched replay response without treating it as live',()=>{
 assert.throws(()=>r.checkedReplayResult({status:'COMPLETED',simulated:true,segments:[]},
  {dataset_id:'btc',dataset_fingerprint:sha,market:'BTC'}));
});
test('decoding selected archive fails closed',()=>{
 assert.throws(()=>r.readSegmentArchive({simulation_result_json:'{}',dataset_fingerprint:sha}));
 assert.throws(()=>r.readSegmentArchive({simulation_result_json:'{',dataset_fingerprint:sha}));
});
