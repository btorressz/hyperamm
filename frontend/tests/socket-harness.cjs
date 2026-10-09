const path = require("node:path");
const { startTerminalSocket } = require(path.join(process.env.TERMINAL_TEST_BUILD, "utils/terminalSocket.js"));
const valid = require("./fixtures/terminal-valid.json");
function harness({ refreshFixture = false } = {}) {
  const old = { window:global.window, WebSocket:global.WebSocket, location:global.location, now:Date.now };
  let now = Date.parse(valid.emitted_at), id = 0; const timers = new Map(), sockets = [], delays = [];
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
    send(frame) { if (refreshFixture && typeof frame === 'object' && frame?.emitted_at === valid.emitted_at) frame = {...frame, emitted_at:new Date(now).toISOString()}; this.onmessage({data:typeof frame==='string'?frame:JSON.stringify(frame)}); }
    close() { if(this.readyState===3)return;this.closes++;this.readyState=3;this.onclose(); }
  }
  global.WebSocket=Socket;
  const stop=startTerminalSocket();
  return {
    sockets,delays,stop,
    get now() { return now; },
    get timerCount() { return timers.size; },
    advance(ms) { const end=now+ms; while(true) { let next;for(const [key,t] of timers)if(t.at<=end&&(!next||t.at<next[1].at))next=[key,t];if(!next)break;const [key,t]=next;now=t.at;if(t.interval)t.at+=t.delay;else timers.delete(key);t.fn(); }now=end; },
    cleanup() {stop();Date.now=old.now;global.window=old.window;global.WebSocket=old.WebSocket;global.location=old.location;global.clearTimeout=clearT;global.clearInterval=clearI;},
  };
}
module.exports = { harness };
