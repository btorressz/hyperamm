const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { validateTerminal } = require(path.join(process.env.TERMINAL_TEST_BUILD, 'utils/validateTerminal.js'));
const { startTerminalSocket } = require(path.join(process.env.TERMINAL_TEST_BUILD, 'utils/terminalSocket.js'));
const { useTerminalStore: store } = require(path.join(process.env.TERMINAL_TEST_BUILD, 'stores/terminal.js'));
const valid = require('./fixtures/terminal-valid.json');
const unavailable = require('./fixtures/terminal-unavailable.json');
const malformed = require('./fixtures/terminal-malformed.json');
const initial = store.getInitialState();
afterEach(() => store.setState(initial, true));
function mutate(source, change) {
  const frame = structuredClone(source), parts = change.path.split('.');
  const key = parts.pop();
  let parent = frame;
  for (const part of parts) parent = parent[part];
  if (change.remove) delete parent[key]; else parent[key] = change.value;
  return frame;
}
test('backend PAPER and unavailable TESTNET fixtures satisfy phase12-v1', () => {
  assert.equal(validateTerminal(valid), valid);
  assert.equal(validateTerminal(unavailable), unavailable);
  assert.equal(unavailable.fair_value, null);
  assert.equal(unavailable.vault.net_pnl_quote, null);
});
for (const change of malformed) test(`contract rejects ${change.name}`, () => {
  assert.throws(() => validateTerminal(mutate(valid, change)), /Invalid/);
});
test('all serialized nullable/default fields are required at every populated nesting level', () => {
  function walk(value, parts = []) {
    if (Array.isArray(value)) return value.forEach((v,i) => walk(v,[...parts,String(i)]));
    if (!value || typeof value !== 'object') return;
    for (const [key, child] of Object.entries(value)) {
      // Dynamic records can lose a key; model objects cannot lose a field.
      const dynamic = ['evidence','source_statuses','deviations_bps','deviation_magnitudes_bps','status_counts','subsystems'];
      if (!dynamic.includes(parts.at(-1))) {
        const frame = mutate(valid, {path:[...parts,key].join('.'), remove:true});
        assert.throws(() => validateTerminal(frame), undefined, [...parts,key].join('.'));
      }
      walk(child,[...parts,key]);
    }
  }
  walk(valid);
});
function harness() {
  const old = { window:global.window, WebSocket:global.WebSocket, location:global.location, now:Date.now };
  let now = 10000, id = 0; const timers = new Map(), sockets = [], delays = [];
  Date.now = () => now;
  const schedule = (fn, delay, interval=false) => { const key=++id; timers.set(key,{fn,at:now+delay,delay,interval}); return key; };
  global.window = {
    setTimeout(fn, delay) { delays.push(delay); return schedule(fn,delay); },
    setInterval(fn, delay) { return schedule(fn,delay,true); },
  };
  const clearT=global.clearTimeout, clearI=global.clearInterval;
  global.clearTimeout=global.clearInterval=(key)=>timers.delete(key);
  global.location={protocol:'https:',host:'terminal.test'};
  class Socket {
    static OPEN=1; static CONNECTING=0;
    constructor(url) { this.url=url;this.readyState=0;this.closes=0;sockets.push(this); }
    open() { this.readyState=1;this.onopen(); }
    send(frame) { this.onmessage({data:typeof frame==='string'?frame:JSON.stringify(frame)}); }
    close() { if(this.readyState===3)return;this.closes++;this.readyState=3;this.onclose(); }
  }
  global.WebSocket=Socket;
  const stop=startTerminalSocket();
  return {
    sockets,delays,stop,
    advance(ms) { const end=now+ms; while(true) { let next;for(const [key,t] of timers)if(t.at<=end&&(!next||t.at<next[1].at))next=[key,t];if(!next)break;const [key,t]=next;now=t.at;if(t.interval)t.at+=t.delay;else timers.delete(key);t.fn(); }now=end; },
    cleanup() {stop();Date.now=old.now;global.window=old.window;global.WebSocket=old.WebSocket;global.location=old.location;global.clearTimeout=clearT;global.clearInterval=clearI;},
  };
}
test('malformed frames preserve last valid state/time and ERROR cannot defeat stale reconnect', () => {
  const h=harness();try {
    const s=h.sockets[0];s.open();s.send(valid);const accepted=store.getState().terminal, time=store.getState().lastValidFrameAt;
    for(let i=0;i<6;i++) {h.advance(1000);s.send(i%2 ? '{bad json' : mutate(valid,malformed[9]));}
    assert.equal(store.getState().terminal,accepted);assert.equal(store.getState().lastValidFrameAt,time);
    assert.equal(s.closes,1);assert.deepEqual(h.delays,[1500]);h.advance(1500);assert.equal(h.sockets.length,2);
  }finally{h.cleanup();}
});
test('never-valid malformed stream reconnects with bounded exponential backoff', () => {
  const h=harness();try {
    for(let i=0;i<6;i++) {
      const s=h.sockets.at(-1);s.open();
      for(let j=0;j<6;j++){s.send('null');h.advance(1000);}
      assert.equal(s.closes,1);h.advance(h.delays.at(-1));
    }
    assert.deepEqual(h.delays,[1500,3000,6000,10000,10000,10000]);
    assert.equal(store.getState().terminal,null);assert.equal(store.getState().lastValidFrameAt,null);
  }finally{h.cleanup();}
});
test('valid recovery resets backoff; cleanup cancels reconnect and watchdog', () => {
  const h=harness();try {
    h.sockets[0].open();h.advance(6000);h.advance(1500);
    const s=h.sockets.at(-1);s.open();s.send(valid);s.send('{broken');
    assert.equal(store.getState().wsState,'error');
    h.advance(2000);s.send({...valid,sequence:valid.sequence+1});
    assert.equal(store.getState().wsState,'connected');assert.equal(store.getState().payloadError,null);
    h.advance(6000);assert.equal(h.delays.at(-1),1500);
    const count=h.sockets.length;h.stop();h.advance(30000);assert.equal(h.sockets.length,count);
  }finally{h.cleanup();}
});
test('sequence rejection does not refresh valid time; gaps, restart and session changes remain supported', () => {
  const h=harness();try {
    const s=h.sockets[0];s.open();s.send(valid);const time=store.getState().lastValidFrameAt;
    h.advance(1000);s.send(valid);assert.equal(store.getState().lastValidFrameAt,time);assert.equal(store.getState().wsState,'error');
    s.send({...valid,sequence:valid.sequence+3});assert.match(store.getState().connectionNotice,/gap/);
    s.send({...valid,process_id:'restarted',sequence:1});assert.match(store.getState().connectionNotice,/restarted/);
    s.send({...valid,process_id:'restarted',session_id:'new-session',sequence:2});assert.match(store.getState().connectionNotice,/session/);
  }finally{h.cleanup();}
});

test('a socket that never opens times out; obsolete and cleaned-up sockets cannot update state', () => {
  const h=harness();try {
    const first=h.sockets[0];h.advance(6000);assert.equal(first.closes,1);
    h.advance(1500);const current=h.sockets.at(-1);current.open();current.send(valid);
    const accepted=store.getState().terminal;
    first.send({...valid,sequence:valid.sequence+10});assert.equal(store.getState().terminal,accepted);
    h.stop();current.send({...valid,sequence:valid.sequence+20});assert.equal(store.getState().terminal,accepted);
  }finally{h.cleanup();}
});

test('every malformed fixture and malformed JSON retains the last accepted frame', () => {
  const h=harness();try {
    const s=h.sockets[0];s.open();s.send(valid);
    const accepted=store.getState().terminal,time=store.getState().lastValidFrameAt;
    assert.ok(accepted);
    for(const change of malformed) {
      s.send(mutate(valid,change));
      assert.equal(store.getState().terminal,accepted,change.name);
      assert.equal(store.getState().lastValidFrameAt,time,change.name);
      assert.equal(store.getState().wsState,'error',change.name);
    }
    for(const data of ['{bad JSON','null','[]','42','"string"']) {
      s.send(data);assert.equal(store.getState().terminal,accepted);
      assert.equal(store.getState().lastValidFrameAt,time);
    }
  }finally{h.cleanup();}
});
