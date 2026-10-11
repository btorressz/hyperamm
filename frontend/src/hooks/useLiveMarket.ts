import { useEffect, useRef, useState } from 'react';
import { useLiveMarketStore } from '../stores/liveMarkets';
import { startLiveMarketSocket } from '../utils/liveMarketSocket';
export function useLiveMarket() {
  const s=useLiveMarketStore();
  const controller=useRef<ReturnType<typeof startLiveMarketSocket> | null>(null);
  const [now,setNow]=useState(()=>performance.now());
  useEffect(()=>{
    const live=startLiveMarketSocket(s.selectedLiveMarket,s.selectionEpoch);controller.current=live;
    const timer=setInterval(()=>setNow(performance.now()),1000);
    return ()=>{clearInterval(timer);live.stop();if(controller.current===live)controller.current=null;};
  },[s.selectedLiveMarket,s.selectionEpoch]);
  return {s,now,retry:()=>controller.current?.retry()};
}
