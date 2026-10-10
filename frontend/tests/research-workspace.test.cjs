const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const read = p => require(path.join(process.env.TERMINAL_TEST_BUILD,p));
const {AgentDetails,agentCounts} = read('components/agents/AgentDetails.js');
const {AgentAuthoritySummary} = read('components/agents/AgentAuthoritySummary.js');
const {AgentEventList} = read('components/agents/AgentEvents.js');
const {VaultSummary,accountingNumber} = read('components/VaultSummary.js');
const {PnlBreakdown} = read('components/PnlBreakdown.js');
const {AccountingConsistency} = read('components/vault/AccountingConsistency.js');
const {AccountingProvenance} = read('components/vault/AccountingProvenance.js');
const {AccountingLedger,LedgerDetails,selectLedger} = read('components/AccountingLedger.js');
const {checkedLedger,ledgerKey,ledgerMatches,checkedAgentEvents,sessionCurrent} = read('utils/researchEvidence.js');
const {useTerminalStore:store} = read('stores/terminal.js');
const {api} = read('api/client.js');
const valid = require('./fixtures/terminal-valid.json');
const render = (C,props) => renderToStaticMarkup(React.createElement(C,props));
const frame = () => ({...structuredClone(valid),emitted_at:new Date().toISOString()});
const ledger = t => ({mode:t.vault.mode,market:t.vault.market,ledger_version:t.vault.ledger_version,ledger_fingerprint:t.vault.ledger_fingerprint,order:'newest-first',retention_policy:'HALT_WHEN_FULL',entries:[]});
const entry = (sequence,patch={}) => ({sequence,event_id:'event-'+sequence,event_type:'TRADE_FILL',timestamp:valid.emitted_at,market:'ETH',side:'BID',price:'3000.00000000000000001',size:'0.00000000000000001',cash_delta_quote:'-0.00000000000000000001',position_delta_base:'0.00000000000000001',fee_delta_quote:'0',funding_delta_quote:'0',realized_pnl_delta:'0',cash_balance_quote:'9999.99999999999999999999',position_base:'0.00000000000000001',average_entry_price:'3000.00000000000000001',cumulative_realized_pnl:'0',cumulative_fees:'0',cumulative_funding:'0',source:'PAPER_FILL',simulated:true,event_fingerprint:'event-fingerprint-full',previous_ledger_fingerprint:'previous-full',ledger_fingerprint:'current-full',...patch});
const all = {event:'ALL',side:'ALL',source:'ALL',simulation:'ALL'};
for (const [field,title] of [['regime','Regime v2'],['toxic_flow','Toxic Flow v2'],['execution_quality','Execution Quality v2'],['liquidity_quality','Liquidity Quality'],['perp_crowding','Perp Crowding'],['predictive_adverse_selection','Predictive Adverse Selection']]) {
 test('workspace renders '+title+' with inspectable evidence and separate recommendation',()=>{
  const t=frame(),html=render(AgentDetails,{t,historical:false});
  assert.ok(html.includes(title));assert.match(html,/View details/);assert.match(html,/Observation/);assert.match(html,/Recommendation/);assert.match(html,/backend reasons/);
  t.agents[field]=null;
  assert.match(render(AgentDetails,{t,historical:false}),/UNAVAILABLE/);
 });
}
for (const health of ['WARMING_UP','INSUFFICIENT_DATA','DEGRADED','ERROR']) test('agent health preserves '+health,()=>{
 const t=frame();t.agents.regime.health=health;t.agents.regime.reasons=['backend-only threshold explanation'];
 const html=render(AgentDetails,{t,historical:false});assert.ok(html.includes(health));assert.ok(html.includes('backend-only threshold explanation'));
});
test('missing supervisor does not suppress six agent cards or fabricate health counts',()=>{
 const t=frame();t.agents.supervisor=null;
 t.agents.regime.health='ERROR';t.agents.toxic_flow=null;
 const counts=agentCounts(t);assert.equal(counts.available+counts.unavailable,6);assert.equal(counts.degraded,1);
 const html=render(AgentDetails,{t,historical:false});assert.match(html,/Regime v2/);assert.match(html,/Predictive Adverse Selection/);
});
test('unavailable confidence and zero-fill markouts never mean zero toxicity',()=>{
 const t=frame();t.agents.regime.confidence=null;t.agents.toxic_flow.metrics.matured_fills=0;
 const html=render(AgentDetails,{t,historical:false});assert.match(html,/Unavailable from current evidence/);assert.match(html,/Missing markouts do not establish zero toxicity/);
});
test('shadow remains non-authoritative with unavailable model provenance',()=>{
 const html=render(AgentDetails,{t:frame(),historical:false});
 for(const text of ['ML SHADOW','OBSERVATIONAL ONLY','NO EXECUTION AUTHORITY','NO QUOTE AUTHORITY','conditional on fill','not validated prediction accuracy']) assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/ADVISORY|ACTIVE|validated accuracy: 100/);
});
test('single OI observation never establishes trend',()=>{
 const t=frame();t.agents.perp_crowding={...t.agents.regime,agent:'PERP_CROWDING',metrics:{observation_count:1,oi_change_ratio:'0.999',funding_rate_delta:'0.888',long_crowding_score:'0',short_crowding_score:'0',basis_stress_score:'0'}};
 const html=render(AgentDetails,{t,historical:false});assert.doesNotMatch(html,/99.9%/);assert.match(html,/single open-interest observation does not establish a trend/);
});
test('matching authorization fingerprint is separate from recommendation and reported fills',()=>{
 const t=frame();t.risk_authorization.agent_fingerprint=t.agents.agent_fingerprint;t.risk_authorization.agent_version=t.agents.agent_version;
 const html=render(AgentAuthoritySummary,{t,historical:false});
 for(const text of ['Agent recommendation','Risk evaluation','Final authorization','Execution evidence','Exact per-agent causal attribution is unavailable','binds the displayed agent version']) assert.ok(html.includes(text),text);
 t.risk_authorization.agent_version++;
 assert.match(render(AgentAuthoritySummary,{t,historical:false}),/Matching agent authorization lineage unavailable/);
});
test('historical authorization is last-known and never promoted by enabled supervisor',()=>{
 const t=frame();t.risk_authorization.authorized=true;
 assert.match(render(AgentAuthoritySummary,{t,historical:true}),/LAST · .*AUTHORIZED/);
 assert.match(render(AgentDetails,{t,historical:true}),/HISTORICAL/);
});
const events=Array.from({length:250},(_,i)=>({timestamp:valid.emitted_at,agent:i%2?'REGIME':'SUPERVISOR',previous_state:'WARMING_UP',new_state:'READY',reasons:['Backend reason '+i],version:i}));
test('events are agent-filtered and bounded without counting horizons as fills',()=>{
 assert.equal(checkedAgentEvents(events,'REGIME',100).length,100);
 assert.ok(checkedAgentEvents(events,'REGIME').every(e=>e.agent==='REGIME'));
 assert.equal(checkedAgentEvents(events,undefined,999).length,250);
 assert.throws(()=>checkedAgentEvents([...events,events[0]]),/incompatible/);
 assert.throws(()=>checkedAgentEvents([{...events[0],reasons:[1]}]),/incompatible/);
});
test('event list preserves transition, backend reason, timestamp and version',()=>{
 const html=render(AgentEventList,{events:[events[3]]});
 for(const text of ['REGIME','WARMING_UP','READY','Backend reason 3','agent v3',valid.emitted_at]) assert.ok(html.includes(text));
 assert.match(render(AgentEventList,{events:[]}),/No retained agent events match/);
});
test('typed event endpoint uses filtering, bounded limit and AbortSignal',async()=>{
 const before=global.fetch,signal=new AbortController().signal;let args;
 try{global.fetch=async(...x)=>{args=x;return {ok:true,json:async()=>[]}};await api.agentEvents('REGIME',999,signal);assert.equal(args[0],'/api/v1/agents/events?limit=250&agent=REGIME');assert.equal(args[1].signal,signal);}
 finally{global.fetch=before;}
});
test('PAPER capital is simulated and all reported decimal precision remains exact',()=>{
 const t=frame();t.vault.equity_quote='10000000000000000.0000000000000001';
 const html=render(VaultSummary,{vault:t.vault});assert.ok(html.includes(t.vault.equity_quote));assert.match(html,/PAPER \/ SIMULATED/);assert.match(html,/Reserved Capital/);
});
test('TESTNET partial capital and missing PnL stay unavailable',()=>{
 const t=frame();Object.assign(t.vault,{mode:'TESTNET',accounting_complete:'PARTIAL',initial_equity_quote:null,settled_capital_quote:null,available_capital_quote:null,equity_quote:null});
 assert.match(render(VaultSummary,{vault:t.vault}),/TESTNET \/ PARTIAL/);assert.match(render(VaultSummary,{vault:t.vault}),/Unavailable/);
 const pnl=Object.fromEntries(Object.keys(t.accounting.pnl).map(k=>[k,null]));assert.match(render(PnlBreakdown,{pnl,vault:t.vault}),/Unavailable/);assert.doesNotMatch(render(PnlBreakdown,{pnl,vault:t.vault}),/<strong>0<\/strong>/);
});
for(const [value,expected,percent] of [[null,'Unavailable'],[undefined,'Unavailable'],['NaN','Unavailable'],['1e-20','0.00000000000000000001'],['-0.00000000000000001','-0.00000000000000001'],['9007199254740993.01','9007199254740993.01'],['0.00000000000000001','0.000000000000001%',true]]) test('accounting decimal display preserves '+String(value),()=>assert.equal(accountingNumber(value,percent),expected));
test('ledger details preserve every identity and exact financial value',()=>{
 const e=entry(1),html=render(LedgerDetails,{entry:e});
 for(const v of Object.values(e)) if(typeof v==='string') assert.ok(html.includes(v),v);
 assert.match(html,/previous ledger fingerprint/);assert.match(html,/cumulative funding/);
 assert.match(render(AccountingLedger,{ledger:{...ledger(frame()),entries:[e]},mode:'PAPER'}),/View ledger entry 1/);
});
test('ledger filter combinations preserve authoritative newest-first source sequence',()=>{
 const entries=[entry(3),entry(2,{event_type:'FEE',side:null,source:'PAPER_CONFIG'}),entry(1,{side:'ASK',simulated:false,source:'VENUE'})];
 assert.deepEqual(selectLedger(entries,all).map(e=>e.sequence),[3,2,1]);
 for(const [field,value,seq] of [['event','FEE',2],['side','NONE',2],['side','ASK',1],['source','VENUE',1],['simulation','NON_SIMULATED',1]]) assert.deepEqual(selectLedger(entries,{...all,[field]:value}).map(e=>e.sequence),[seq]);
 assert.equal(selectLedger(entries,{...all,event:'FEE',side:'BID'}).length,0);
 assert.deepEqual(entries.map(e=>e.sequence),[3,2,1]);
});
test('ledger empty, filter-empty and unavailable states remain distinct',()=>{
 assert.match(render(AccountingLedger,{ledger:ledger(frame()),mode:'PAPER'}),/No accounting events have been booked in this research session/);
 assert.match(render(AccountingLedger,{ledger:ledger(frame()),mode:'TESTNET'}),/Complete authoritative TESTNET fill accounting is unavailable/);
 assert.match(render(AccountingLedger,{ledger:undefined,mode:'PAPER'}),/Current ledger evidence is unavailable/);
});
for(const status of ['CONSISTENT','DIVERGED','UNAVAILABLE']) test('backend consistency state is preserved: '+status,()=>{
 const t=frame();t.vault.execution_accounting.status=status;t.vault.execution_accounting.reason='backend reason';
 if(status==='UNAVAILABLE')t.vault.execution_accounting.execution_accounting_consistent=null;
 const html=render(AccountingConsistency,{vault:t.vault,historical:false});assert.ok(html.includes(status));assert.ok(html.includes('backend reason'));
 if(status==='DIVERGED')assert.match(html,/role="alert"/);
 if(status==='UNAVAILABLE')assert.match(html,/Not authoritative/);
 assert.doesNotMatch(html,/<button/);
});
test('full accounting provenance identities are inspectable without repair controls',()=>{
 const t=frame(),html=render(AccountingProvenance,{t});
 for(const text of [t.process_id,t.session_id,t.vault.accounting_fingerprint,t.vault.ledger_fingerprint,'Inspect full accounting identities','no terminal session ID'])assert.ok(html.includes(text));
 assert.doesNotMatch(html,/<button/);
});
test('ledger key binds process/session as well as context, version and fingerprint',()=>{
 const t=frame(),key=ledgerKey(t);
 for(const mutate of [x=>x.process_id+='new',x=>x.session_id+='new',x=>x.vault.mode='TESTNET',x=>x.vault.market='BTC',x=>x.vault.ledger_version++,x=>x.vault.ledger_fingerprint+='new']) {const next=structuredClone(t);mutate(next);assert.notDeepEqual(ledgerKey(next),key);}
});
for(const field of ['mode','market','ledger_version','ledger_fingerprint'])test('ledger rejects response '+field+' mismatch',()=>{
 const t=frame(),data=ledger(t);data[field]=typeof data[field]==='number'?data[field]+1:data[field]+'mismatch';
 assert.equal(ledgerMatches(data,t),false);assert.throws(()=>checkedLedger(data,t,{terminal:t,wsState:'connected'}),/changed/);
});
for(const transition of ['session','restart','fingerprint','version','disconnect','stale','future']) test('in-flight ledger rejects '+transition+' before visible attribution',async()=>{
 const expected=frame(),response=ledger(expected),current={terminal:structuredClone(expected),wsState:'connected'};
 let resolve;const request=new Promise(r=>resolve=r).then(data=>checkedLedger(data,expected,current));
 if(transition==='session')current.terminal.session_id='replacement';
 if(transition==='restart')current.terminal.process_id='replacement';
 if(transition==='fingerprint')current.terminal.vault.ledger_fingerprint='replacement';
 if(transition==='version')current.terminal.vault.ledger_version++;
 if(transition==='disconnect')current.wsState='disconnected';
 if(transition==='stale')current.terminal.emitted_at='2001-01-01T00:00:00Z';
 if(transition==='future')current.terminal.emitted_at='2099-01-01T00:00:00Z';
 resolve(response);await assert.rejects(request,/changed/);
});
test('matching current ledger remains read-only and source values are unchanged',()=>{
 const t=frame(),data=ledger(t),before=structuredClone(data);
 assert.equal(checkedLedger(data,t,{terminal:t,wsState:'connected'}),data);assert.deepEqual(data,before);
 assert.equal(sessionCurrent(t,{terminal:t,wsState:'connected'}),true);
});
test('side toxicity remains unavailable without side sample support',()=>{
 const t=frame();t.agents.toxic_flow.metrics.matured_fills=5;t.agents.toxic_flow.metrics.bid_confidence='0';t.agents.toxic_flow.metrics.ask_confidence='0.5';
 const html=render(AgentDetails,{t,historical:false});
 assert.match(html,/BID toxicity<\/span><strong>Unavailable from current evidence/);
});
