const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const {YahooObservationView}=require(path.join(process.env.TERMINAL_TEST_BUILD,'components/YahooObservationPanel.js'));
const {api}=require(path.join(process.env.TERMINAL_TEST_BUILD,'api/client.js'));
const {validateTerminal}=require(path.join(process.env.TERMINAL_TEST_BUILD,'utils/validateTerminal.js'));
const valid=require('./fixtures/terminal-valid.json');
const observation={provider:'YAHOO_FINANCE',symbol:'ETH-USD',role:'OBSERVATIONAL',authority:'NONE',price:'3000',source_timestamp:'2026-10-09T01:00:00Z',age_ms:10,healthy:true,stale:false,status:'HEALTHY',error:null,deviations_bps:{yahoo_vs_core_consensus_bps:'12.34'}};
function render(data,error=false){return renderToStaticMarkup(React.createElement(YahooObservationView,{data,error}));}
test('Yahoo healthy observation shows source time and explicit lack of authority',()=>{
 const html=render(observation);
 for(const label of ['Observational Only','Authority NONE','Not execution-authoritative','ETH-USD','3,000','12.34 bps','10 ms']) assert.ok(html.includes(label),label);
});
for(const status of ['DISABLED','DEGRADED','STALE','ERROR']) test(`Yahoo ${status} suppresses retained price and deviation`,()=>{
 const html=render({...observation,status,healthy:false,stale:status==='STALE'});
 assert.ok(html.includes(status)&&html.includes('Unavailable'));
 assert.ok(!html.includes('3,000')&&!html.includes('12.34 bps'));
 assert.ok(html.includes('Authority NONE'));
});
test('Yahoo stale flag suppresses even inconsistent healthy data',()=>{
 const html=render({...observation,stale:true});
 assert.ok(!html.includes('3,000')&&!html.includes('12.34 bps'));
});
test('Yahoo loading, unavailable and request error remain safe',()=>{
 assert.ok(render(null).includes('Loading observation diagnostics'));
 assert.ok(render({...observation,price:null,healthy:false,source_timestamp:null,deviations_bps:{yahoo_vs_core_consensus_bps:null}}).includes('Unavailable'));
 assert.ok(render(null,true).includes('Observation diagnostics unavailable'));
});
test('separate observation request handles disabled data and HTTP failures',async()=>{
 const original=global.fetch;
 try {
  global.fetch=async url=>{
   assert.equal(url,'/api/v1/references/observations');
   return {ok:true,status:200,json:async()=>({market:'ETH',authority:'NONE',observations:[{...observation,status:'DISABLED',healthy:false,price:null}]})};
  };
  const response=await api.referenceObservations();
  assert.equal(response.authority,'NONE');assert.equal(response.observations[0].status,'DISABLED');
  global.fetch=async()=>({ok:false,status:503,json:async()=>({detail:'unavailable'})});
  await assert.rejects(api.referenceObservations(),/unavailable/);
 } finally {global.fetch=original;}
});
test('terminal material PriceEvidence continues rejecting Yahoo identity',()=>{
 const payload=structuredClone(valid);
 const evidence=Object.values(payload.references.evidence)[0];
 evidence.provider='YAHOO_FINANCE';
 assert.throws(()=>validateTerminal(payload),/Invalid/);
});
