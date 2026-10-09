const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = process.env.TERMINAL_TEST_BUILD;
const { useTerminalStore: store } = require(path.join(root, 'stores/terminal.js'));
const { startTerminalSocket } = require(path.join(root, 'utils/terminalSocket.js'));
const { currentSourcePrices, displayedTerminal } = require(path.join(root, 'utils/freshness.js'));
const { RETIRED_IDENTITY_CAPACITY: CAP, DIAGNOSTIC_COUNT_MAX } = require(path.join(root, 'utils/terminalIntegrity.js'));
const { harness } = require('./socket-harness.cjs');
const valid = require('./fixtures/terminal-valid.json');
const initial = store.getInitialState(), NOW = Date.parse(valid.emitted_at);
afterEach(() => store.setState(initial, true));
const frame = (patch={}) => ({...structuredClone(valid), emitted_at:new Date(NOW).toISOString(), ...patch});
const accept = (f, now=NOW) => store.getState().setTerminal(f, now);
function preserved(before) {
  const after=store.getState();
  for(const key of ['terminal','lastSequence','lastEmittedAtMs','lastValidFrameAt','retiredIdentities','retiredProcesses','terminalContractVersion']) assert.equal(after[key],before[key],key);
  assert.notEqual(after.wsState,'connected');
}
const timestampCases = [
  ['current', new Date(NOW).toISOString(), null],
  ['maximum age', new Date(NOW-5000).toISOString(), null],
  ['just stale', new Date(NOW-5001).toISOString(), 'stale'],
  ['ancient 2001', '2001-01-01T00:00:00Z', 'stale'],
  ['future 2099', '2099-01-01T00:00:00Z', 'future'],
  ['future skew boundary', new Date(NOW+2000).toISOString(), null],
  ['just beyond future skew', new Date(NOW+2001).toISOString(), 'future'],
  ['UTC-equivalent offset', new Date(NOW+3600000).toISOString().replace('Z','+01:00'), null],
  ['malformed', 'not-a-date', 'schema'],
  ['impossible calendar day', '2026-02-30T00:00:00Z', 'schema'],
  ['invalid timestamp type', NOW, 'schema'],
  ['missing timezone', '2026-10-07T12:00:00', 'schema'],
  ['invalid offset', '2026-10-07T12:00:00+24:00', 'schema'],
  ['invalid leap day', '2025-02-29T00:00:00Z', 'schema'],
  ['invalid month', '2026-13-01T00:00:00Z', 'schema'],
];
for(const [name,emitted_at,reason] of timestampCases) test(`timestamp policy: ${name}`, () => {
  const before=store.getState(), result=accept(frame({emitted_at}));
  assert.equal(result.accepted,reason===null);
  if(reason) {assert.equal(result.reason,reason);preserved(before);assert.equal(store.getState().rejectedFrames[reason],1);}
  else assert.equal(store.getState().lastValidFrameAt,NOW);
});
for(const [name,emitted_at,reason] of timestampCases.filter(x=>x[2])) test(`higher sequence cannot bypass ${name}`, () => {
  assert.equal(accept(frame()).accepted,true);const before=store.getState();
  assert.deepEqual(accept(frame({sequence:999,emitted_at}),NOW),{accepted:false,reason});preserved(before);
});
test('store enforces complete nested schema', () => {
  const f=frame();f.agents.regime.confidence='NaN';assert.equal(accept(f).reason,'schema');assert.equal(store.getState().terminal,null);
});
for(const [name,sequence,accepted] of [['increase',11,true],['duplicate',10,false],['regression',9,false],['gap',20,true]]) test(`same identity sequence: ${name}`, () => {
  accept(frame({sequence:10}));const before=store.getState();assert.equal(accept(frame({sequence}),NOW+1).accepted,accepted);
  if(!accepted) preserved(before);if(name==='gap') assert.match(store.getState().connectionNotice,/gap/);
});
test('higher sequence with regressed emission rejected; equal emission permitted', () => {
  accept(frame());const before=store.getState();assert.equal(accept(frame({sequence:2,emitted_at:new Date(NOW-1).toISOString()})).reason,'timeRegression');preserved(before);
  assert.equal(accept(frame({sequence:2})).accepted,true);
});
test('same-process session changes preserve process sequence and time watermarks', () => {
  accept(frame({sequence:50}));const before=store.getState();
  assert.equal(accept(frame({session_id:'B',sequence:1})).reason,'sequence');preserved(before);
  assert.equal(accept(frame({session_id:'B',sequence:51,emitted_at:new Date(NOW-1).toISOString()})).reason,'timeRegression');preserved(before);
  assert.deepEqual(accept(frame({session_id:'B',sequence:51})),{accepted:true,restarted:false});assert.match(store.getState().connectionNotice,/session changed/);
});
test('A to B to A replay rejected even with higher sequence and fresh time', () => {
  accept(frame());accept(frame({session_id:'B',sequence:2}));const before=store.getState();assert.equal(accept(frame({sequence:3}),NOW+1).reason,'replay');preserved(before);
});
test('new process resets ordering; retired process with unknown session rejected', () => {
  accept(frame({sequence:100}));assert.deepEqual(accept(frame({process_id:'new-process',session_id:'B',sequence:1,emitted_at:new Date(NOW-1).toISOString()})),{accepted:true,restarted:true});
  const before=store.getState();assert.equal(accept(frame({session_id:'unknown',sequence:101})).reason,'replay');preserved(before);
  assert.equal(accept(frame({process_id:'new-process',session_id:'B',sequence:2})).accepted,true);
});
test('rejected transition cannot retire active identity or clear freshness error', () => {
  accept(frame());const before=store.getState();assert.equal(accept(frame({process_id:'bad',emitted_at:'2001-01-01T00:00:00Z'})).reason,'stale');preserved(before);
  accept(frame({sequence:2,emitted_at:'2099-01-01T00:00:00Z'}));preserved(before);
  assert.match(store.getState().payloadError,/clock/);assert.equal(accept(frame({sequence:2})).accepted,true);
});
test('retired session FIFO capacity/eviction retains process watermark protection', () => {
  for(let i=0;i<=CAP;i++) assert.equal(accept(frame({session_id:`s${i}`,sequence:i+1})).accepted,true);
  assert.equal(store.getState().retiredIdentities.length,CAP);assert.equal(accept(frame({session_id:'s0',sequence:CAP+2})).reason,'replay');
  accept(frame({session_id:'next',sequence:CAP+2}));assert.equal(store.getState().retiredIdentities.length,CAP);assert.equal(store.getState().retiredIdentities[0].sessionId,'s1');
  assert.equal(accept(frame({session_id:'s0',sequence:1})).reason,'sequence');
  assert.equal(accept(frame({session_id:'s0',sequence:CAP+3,emitted_at:'2001-01-01T00:00:00Z'})).reason,'stale');
  // Finite memory is not authentication: aged-out identity with fresh,
  // increasing evidence can be accepted, as documented.
  assert.equal(accept(frame({session_id:'s0',sequence:CAP+3})).accepted,true);
});
test('retired process FIFO bounded independently from same-process session churn', () => {
  for(let i=0;i<=CAP;i++) accept(frame({process_id:`p${i}`,session_id:'s',sequence:1}));
  assert.equal(store.getState().retiredProcesses.length,CAP);assert.equal(accept(frame({process_id:'p0',session_id:'other'})).reason,'replay');
  for(let i=1;i<=CAP+1;i++) accept(frame({process_id:`p${CAP}`,session_id:`s${i}`,sequence:i+1}));
  assert.equal(accept(frame({process_id:'p0',session_id:'other'})).reason,'replay');
  accept(frame({process_id:'next-process'}));assert.equal(store.getState().retiredProcesses[0],'p1');
  assert.equal(accept(frame({process_id:'p0',emitted_at:'2001-01-01T00:00:00Z'})).reason,'stale');
});
test('diagnostic counters saturate', () => {
  store.setState({rejectedFrames:{...initial.rejectedFrames,stale:DIAGNOSTIC_COUNT_MAX}});accept(frame({emitted_at:'2001-01-01T00:00:00Z'}));assert.equal(store.getState().rejectedFrames.stale,DIAGNOSTIC_COUNT_MAX);
});
function withSocket(fn) { const h=harness();try {fn(h);} finally {h.cleanup();} }
const currentFrame = (h,patch={}) => frame({emitted_at:new Date(h.now).toISOString(),...patch});
test('handshake and invalid first frame never establish connected observation', () => withSocket(h => {
  h.sockets[0].open();assert.equal(store.getState().wsState,'connecting');assert.equal(store.getState().lastValidFrameAt,null);
  h.sockets[0].send(currentFrame(h,{emitted_at:'2001-01-01T00:00:00Z'}));assert.equal(store.getState().wsState,'stale');h.advance(6000);assert.equal(h.sockets[0].closes,1);
}));
for(const [name,mutate] of [
  ['invalid JSON',()=>'{bad'],['schema invalid',()=>({})],
  ['stale',h=>currentFrame(h,{sequence:2,emitted_at:'2001-01-01T00:00:00Z'})],
  ['future',h=>currentFrame(h,{sequence:2,emitted_at:'2099-01-01T00:00:00Z'})],
]) test(`socket ${name} cannot renew watchdog or reset backoff`, () => withSocket(h => {
  const first=h.sockets[0];first.open();h.advance(6000);h.advance(1500);const next=h.sockets.at(-1);next.open();next.send(mutate(h));h.advance(6000);
  assert.deepEqual(h.delays,[1500,3000]);assert.equal(store.getState().lastValidFrameAt,null);
}));
test('duplicates cannot renew watchdog or reset recovery backoff', () => withSocket(h => {
  const s=h.sockets[0];s.open();s.send(currentFrame(h));const before=store.getState();s.close();h.advance(1500);
  const next=h.sockets.at(-1);next.open();next.send(currentFrame(h));preserved(before);h.advance(6000);assert.deepEqual(h.delays,[1500,3000]);
}));
test('rejected stream preserves accepted time until watchdog closes', () => withSocket(h => {
  const s=h.sockets[0];s.open();s.send(currentFrame(h));const before=store.getState();
  for(let i=0;i<5;i++){h.advance(1000);s.send(currentFrame(h,{sequence:100,emitted_at:'2099-01-01T00:00:00Z'}));preserved(before);}
  h.advance(1000);assert.equal(s.closes,1);assert.equal(store.getState().lastValidFrameAt,before.lastValidFrameAt);
}));
test('watchdog expires envelope age despite recent arrival', () => withSocket(h => {
  const s=h.sockets[0];s.open();s.send(currentFrame(h,{emitted_at:new Date(h.now-5000).toISOString()}));assert.equal(store.getState().wsState,'connected');h.advance(1000);assert.equal(s.closes,1);
}));
test('close/reconnect stale frame/restart/retired-process replay recovery', () => withSocket(h => {
  const s=h.sockets[0];s.open();s.send(currentFrame(h));const old=store.getState();s.close();h.advance(1500);const next=h.sockets.at(-1);next.open();
  assert.equal(store.getState().lastValidFrameAt,old.lastValidFrameAt);next.send(currentFrame(h,{sequence:2,emitted_at:new Date(h.now-5001).toISOString()}));preserved(old);
  next.send(currentFrame(h,{process_id:'restart',session_id:'B'}));assert.equal(store.getState().wsState,'connected');const fresh=store.getState();next.send(currentFrame(h,{sequence:500}));preserved(fresh);
  h.advance(6000);assert.equal(next.closes,1);
}));
test('replacement controller owns callbacks; repeated close cannot duplicate timers', () => withSocket(h => {
  const first=h.sockets[0];first.open();first.send(currentFrame(h));const stop=startTerminalSocket();try {
    const next=h.sockets.at(-1);next.open();next.send(currentFrame(h,{sequence:2}));const accepted=store.getState();
    first.send(currentFrame(h,{sequence:999}));first.onopen();first.onclose();first.onerror();h.stop();assert.equal(store.getState().terminal,accepted.terminal);assert.equal(store.getState().wsState,'connected');
    next.close();next.onclose();assert.equal(h.delays.length,1);assert.equal(h.timerCount,2);stop();assert.equal(h.timerCount,0);h.advance(30000);assert.equal(h.sockets.length,2);
    next.send(currentFrame(h,{sequence:1000}));assert.equal(store.getState().terminal,accepted.terminal);
  }finally{stop();}
}));
test('StrictMode mount cleanup remount clears first-generation timers', () => withSocket(h => {
  h.stop();assert.equal(h.timerCount,0);const stop=startTerminalSocket();try {
    const s=h.sockets.at(-1);s.open();s.send(currentFrame(h));assert.equal(store.getState().wsState,'connected');stop();assert.equal(h.timerCount,0);assert.equal(store.getState().wsState,'disconnected');
  }finally{stop();}
}));
test('fresh envelope preserves degraded sources and economic authority', () => {
  const f=frame();f.perp_context.stale=true;f.references.evidence.KRAKEN.stale=true;f.references.evidence.KRAKEN.healthy=false;const original=structuredClone(f);assert.equal(accept(f).accepted,true);
  assert.equal(currentSourcePrices(store.getState().terminal).mark_price,null);assert.equal(store.getState().terminal.references.evidence.KRAKEN.stale,true);assert.deepEqual(f,original);
  const shown=displayedTerminal(f,NOW+2000);assert.equal(shown.references.evidence.KRAKEN.stale,true);assert.equal(shown.risk_authorization,f.risk_authorization);assert.equal(shown.risk_firewall,f.risk_firewall);
  assert.equal(shown.references.evidence.KRAKEN.source_timestamp,f.references.evidence.KRAKEN.source_timestamp);
});
test('historical source ages increase without lending health or authorization', () => {
  const f=frame(), original=structuredClone(f), shown=displayedTerminal(f,NOW+10000);
  assert.equal(shown.references.evidence.REDSTONE.age_ms,f.references.evidence.REDSTONE.age_ms+10000);assert.equal(shown.references.evidence.REDSTONE.healthy,f.references.evidence.REDSTONE.healthy);assert.equal(shown.references.evidence.REDSTONE.stale,f.references.evidence.REDSTONE.stale);assert.equal(shown.perp_context.stale,true);
  assert.equal(currentSourcePrices(shown,false).consensus_price,null);assert.equal(currentSourcePrices(shown,false).oracle_price,null);assert.equal(shown.risk_authorization,f.risk_authorization);assert.deepEqual(f,original);
  assert.equal(accept(f,NOW+10000).reason,'stale');assert.equal(store.getState().terminal,null);
});
test('emission regression below browser millisecond precision is rejected', () => {
  const second=new Date(NOW).toISOString().replace(/\.\d+Z$/, '');
  accept(frame({emitted_at:second+'.123456Z'}),NOW+1000);const before=store.getState();
  assert.equal(accept(frame({sequence:2,emitted_at:second+'.123455Z'}),NOW+1000).reason,'timeRegression');preserved(before);
  assert.equal(accept(frame({sequence:2,emitted_at:second+'.1234560Z'}),NOW+1000).accepted,true);
});
test('full ISO fraction cannot hide excessive future skew at millisecond boundary', () => {
  const boundary=new Date(NOW+2000).toISOString();
  assert.equal(accept(frame({emitted_at:boundary.replace('Z','001Z')})).reason,'future');
  assert.equal(accept(frame({emitted_at:boundary})).accepted,true);
});
