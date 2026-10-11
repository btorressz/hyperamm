import type { LiveMarketId, LiveStreamSnapshot } from '../types';
import { api } from '../api/client';
import { useLiveMarketStore } from '../stores/liveMarkets';
import { checkedLiveEnvelope, checkedLiveSnapshot } from './liveMarketEvidence';

export type LiveSocketEnvironment = {
  snapshot: (market: LiveMarketId, signal: AbortSignal) => Promise<LiveStreamSnapshot>;
  socket: (url: string) => WebSocket; monotonic: () => number; wall: () => number;
  later: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>;
  cancel: (timer: ReturnType<typeof setTimeout>) => void;
  events: Pick<Window,'addEventListener'|'removeEventListener'>;
  visible: () => boolean; online: () => boolean; origin: string;
};
function browserEnvironment(): LiveSocketEnvironment {
  return {snapshot:api.liveStreamSnapshot,socket:url=>new WebSocket(url),monotonic:()=>performance.now(),wall:()=>Date.now(),
    later:(fn,ms)=>setTimeout(fn,ms),cancel:timer=>clearTimeout(timer),events:window,
    visible:()=>document.visibilityState==='visible',online:()=>navigator.onLine,
    origin:location.origin.replace(/^http/,'ws')};
}
let activeStop: (()=>void) | undefined;
export function startLiveMarketSocket(market: LiveMarketId, epoch: number, env = browserEnvironment()) {
  activeStop?.();
  const state=()=>useLiveMarketStore.getState();
  let stopped=false, socket: WebSocket | null=null, request: AbortController | null=null,
    retryTimer: ReturnType<typeof setTimeout> | undefined, watchdog: ReturnType<typeof setTimeout> | undefined,
    attempt=0, run=0, lastFrameAt=env.monotonic(), hardStopped=false, boundaryObserver: string | null=null, boundaryGeneration: number | null=null, highestSequence=0;
  // Old identities can never re-enter after a confirmed observer replacement.
  const retiredObservers = new Set<string>();
  const valid = (token: number) => !stopped && token===run && state().selectionEpoch===epoch && state().selectedLiveMarket===market;
  function clearResources() {
    run++; request?.abort();request=null;
    if(retryTimer!==undefined)env.cancel(retryTimer);retryTimer=undefined;
    if(watchdog!==undefined)env.cancel(watchdog);watchdog=undefined;
    if(socket){const old=socket;socket=null;old.onopen=old.onmessage=old.onclose=old.onerror=null;old.close(1000,'Live browser observation retired');}
  }
  function retire(notice: string, status: 'RECONNECTING'|'UNAVAILABLE'|'RESYNCHRONIZING' = 'RECONNECTING', clear=false) {
    clearResources();state().retire(epoch,status,notice,clear);
  }
  function schedule(notice: string, terminal=false) {
    retire(notice,terminal?'UNAVAILABLE':'RECONNECTING');
    if(terminal || attempt>=6){hardStopped=true;state().retire(epoch,'UNAVAILABLE',`${notice} · automatic retries stopped; retry explicitly.`);return;}
    const delay=Math.min(1000*2**attempt++,30000);
    retryTimer=env.later(()=>{retryTimer=undefined;void bootstrap();},delay);
  }
  async function bootstrap() {
    if(stopped || hardStopped)return;
    clearResources();
    if(!env.online() || !env.visible()) {state().retire(epoch,'RECONNECTING','Observation paused while offline or hidden; current evidence retired.');return;}
    state().retire(epoch,'RESYNCHRONIZING','Validating a fresh backend snapshot boundary…');
    const token=run, controller=new AbortController();request=controller;
    const started=env.monotonic();
    watchdog=env.later(()=>{if(valid(token))schedule('Backend snapshot timeout');},10000);
    try {
      const snapshot=checkedLiveSnapshot(await env.snapshot(market,controller.signal),market,env.wall());
      if(!valid(token))return;
      env.cancel(watchdog);watchdog=undefined;request=null;
      if(retiredObservers.has(snapshot.status.observer_instance_id))throw new Error('Retired observer snapshot');
      const previous=boundaryObserver;
      if(previous && previous!==snapshot.status.observer_instance_id){
        retiredObservers.add(previous);
        if(retiredObservers.size>8){schedule('Too many observer replacements',true);return;}
        state().retire(epoch,'RESYNCHRONIZING','Observer restarted; previous evidence retired.',true);
      }
      if(previous===snapshot.status.observer_instance_id && boundaryGeneration!==null && snapshot.status.connection_generation<boundaryGeneration)throw new Error('Retired generation snapshot');
      if(boundaryObserver!==snapshot.status.observer_instance_id || boundaryGeneration!==snapshot.status.connection_generation)highestSequence=0;
      boundaryObserver=snapshot.status.observer_instance_id;boundaryGeneration=snapshot.status.connection_generation;
      const received=env.monotonic();
      if(!state().acceptSnapshot(snapshot,epoch,received,Math.max(0,(received-started)/1000,(env.wall()-Date.parse(snapshot.status.evaluated_at))/1000)))return;
      const backend=snapshot.status.connection_state;
      if(['DISABLED','STOPPED','UNAVAILABLE'].includes(backend)){
        state().retire(epoch,backend==='DISABLED'?'DISABLED':'UNAVAILABLE',backend==='DISABLED'?'Live market observation is disabled by the backend operator.':'Backend observation unavailable; retry when conditions change.');
        return;
      }
      if(['FORBIDDEN','NOT_LISTED','SDK_UNAVAILABLE','CLEANUP_ERROR'].includes(snapshot.status.last_error_code ?? '')) {
        schedule(`Backend observation ${snapshot.status.last_error_code}`,true);return;
      }
      const ws=env.socket(`${env.origin}/ws/live-markets/${market}`);socket=ws;lastFrameAt=env.monotonic();const connectionStarted=lastFrameAt;
      ws.onopen=()=>{/* Transport handshake never makes observations fresh. */};
      ws.onmessage=event=>{
        if(!valid(token) || socket!==ws)return;
        let frame;
        try {
          if(typeof event.data!=='string' || new TextEncoder().encode(event.data).length>65536)throw new Error('Oversized or non-text frame');
          frame=checkedLiveEnvelope(JSON.parse(event.data),market,env.wall());
        } catch {
          state().rejectFrame(epoch,'Rejected invalid live stream frame; last validated evidence retained.');return;
        }
        if(retiredObservers.has(frame.observer_instance_id)) {state().rejectFrame(epoch,'Rejected retired observer frame.');return;}
        const s=state();
        if(frame.observer_instance_id!==s.observerInstanceId || frame.connection_generation!==s.connectionGeneration){
          if(frame.observer_instance_id===s.observerInstanceId && frame.connection_generation<(s.connectionGeneration ?? 0)) {state().rejectFrame(epoch,'Rejected retired generation.');return;}
          if(frame.observer_instance_id===boundaryObserver){boundaryGeneration=Math.max(boundaryGeneration ?? 0,frame.connection_generation);highestSequence=0;}
          retire('Observer/generation changed; retiring current evidence and resynchronizing.','RESYNCHRONIZING',true);
          schedule('Observer/generation changed; fetching a fresh boundary.');return;
        }
        const received=env.monotonic(), transit=Math.max(0,(env.wall()-Date.parse(frame.emitted_at))/1000);
        if(frame.sequence<=highestSequence || !s.acceptFrame(frame,epoch,received,transit)) {state().rejectFrame(epoch,'Rejected replayed or non-increasing publication sequence.');return;}
        lastFrameAt=received;highestSequence=frame.sequence;
        // Do not reset retry budget on a repeatedly failing bootstrap frame.
        if(frame.payload.observation_status==='AVAILABLE' && received-connectionStarted>=30000)attempt=0;
      };
      ws.onclose=event=>{if(valid(token)&&socket===ws)schedule(event.code===1013?'Stream capacity/overflow; resynchronization required.':`Live browser stream disconnected (${event.code}); previous observations retired.`,event.code===1008);};
      ws.onerror=()=>{if(valid(token)&&socket===ws)schedule('Live browser stream unavailable.');};
      function watch() {
        if(!valid(token))return;
        if(env.monotonic()-lastFrameAt>30000){schedule('No validated stream publication within 30 seconds; evidence retired.');return;}
        watchdog=env.later(watch,1000);
      }
      watchdog=env.later(watch,1000);
    } catch {
      if(valid(token))schedule('Live snapshot unavailable or failed validation.');
    }
  }
  function change() {
    if(stopped)return;
    if(!env.online() || !env.visible())retire('Observation paused while offline or hidden; current evidence retired.');
    else if(!hardStopped)void bootstrap();
  }
  for(const event of ['online','offline','visibilitychange','pageshow'])env.events.addEventListener(event,change);
  const stop=()=>{
    if(stopped)return;stopped=true;clearResources();
    for(const event of ['online','offline','visibilitychange','pageshow'])env.events.removeEventListener(event,change);
    if(activeStop===stop){activeStop=undefined;state().retire(epoch,'STOPPED','Live workspace closed; observations retired.');}
  };
  activeStop=stop;void bootstrap();
  return {stop,retry:()=>{if(stopped)return;attempt=0;hardStopped=false;void bootstrap();}};
}
