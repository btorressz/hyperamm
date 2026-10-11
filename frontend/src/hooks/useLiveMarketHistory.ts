import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useLiveMarketStore } from '../stores/liveMarkets';
import { checkedLiveHistory, checkedLiveProviders } from '../utils/liveMarketEvidence';
export function useLiveMarketHistory() {
  const s=useLiveMarketStore(), [limit,setLimit]=useState(300);
  const market=s.selectedLiveMarket, observer=s.observerInstanceId, boundary=s.boundaryVersion;
  function currentBoundary() {
    const current=useLiveMarketStore.getState();
    if(current.selectedLiveMarket!==market || current.selectionEpoch!==s.selectionEpoch || current.observerInstanceId!==observer || current.boundaryVersion!==boundary)throw new Error('Retired observation request');
  }
  const options={enabled:!!observer,retry:false,staleTime:0,gcTime:0,refetchOnWindowFocus:false};
  const history=useQuery({...options,queryKey:['live-history',market,s.selectionEpoch,observer,boundary,limit],
    refetchInterval:5000,
    queryFn:async({signal})=>{
      const result=await api.liveMarketHistory(market,limit,signal);currentBoundary();
      return checkedLiveHistory(result,market,observer!,limit);
    }});
  const providers=useQuery({...options,queryKey:['live-providers',market,s.selectionEpoch,observer,boundary],
    refetchInterval:15000,
    queryFn:async({signal})=>{
      const started=performance.now();
      const result=await api.liveProviderHealth(market,signal);currentBoundary();
      return {health:checkedLiveProviders(result,market),receivedAt:performance.now(),transitSeconds:Math.max(0,(performance.now()-started)/1000)};
    }});
  return {history,providers,limit,setLimit};
}
