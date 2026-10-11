import { create } from 'zustand';
import type { LiveMarketId, LiveMarketStreamEnvelope, LiveStreamSnapshot } from '../types';
import { liveMarketIds, type ReceivedSnapshot } from '../utils/liveMarketEvidence';
export type BrowserStreamStatus = 'STOPPED'|'CONNECTING'|'CONNECTED'|'RECONNECTING'|'UNAVAILABLE'|'DISABLED'|'RESYNCHRONIZING';
type LiveMarkets = {
  selectedLiveMarket: LiveMarketId; selectionEpoch: number; observerInstanceId: string | null;
  connectionGeneration: number | null; latestStreamSequence: number;
  streamStatus: BrowserStreamStatus; evidence: ReceivedSnapshot | null; current: boolean;
  connectionNotice: string | null; lastValidatedAt: number | null; rejectedFrames: number;
  boundaryVersion: number;
  selectMarket: (market: LiveMarketId) => void;
  retire: (epoch: number, status: BrowserStreamStatus, notice: string, clear?: boolean) => void;
  acceptSnapshot: (snapshot: LiveStreamSnapshot, epoch: number, receivedAt: number, transitSeconds: number) => boolean;
  acceptFrame: (frame: LiveMarketStreamEnvelope, epoch: number, receivedAt: number, transitSeconds: number) => boolean;
  rejectFrame: (epoch: number, notice: string) => void;
};
export const useLiveMarketStore = create<LiveMarkets>((set,get) => ({
  selectedLiveMarket:'BTC', selectionEpoch:0, observerInstanceId:null, connectionGeneration:null,
  latestStreamSequence:0, streamStatus:'STOPPED', evidence:null, current:false, connectionNotice:null,
  lastValidatedAt:null, rejectedFrames:0, boundaryVersion:0,
  selectMarket: market => {
    if (!liveMarketIds.includes(market)) throw new Error('Unsupported live market');
    if (market === get().selectedLiveMarket) return;
    set(s => ({selectedLiveMarket:market,selectionEpoch:s.selectionEpoch+1,observerInstanceId:null,
      connectionGeneration:null,latestStreamSequence:0,evidence:null,current:false,streamStatus:'CONNECTING',
      connectionNotice:null,lastValidatedAt:null,rejectedFrames:0,boundaryVersion:s.boundaryVersion+1}));
  },
  retire: (epoch, streamStatus, connectionNotice, clear=false) => {
    if (epoch !== get().selectionEpoch) return;
    set(s=>({streamStatus,connectionNotice,current:false,
      ...(clear ? {evidence:null,observerInstanceId:null,connectionGeneration:null,latestStreamSequence:0} : {}),
      boundaryVersion:s.boundaryVersion+1}));
  },
  acceptSnapshot: (snapshot,epoch,receivedAt,transitSeconds) => {
    const s=get(); if (epoch!==s.selectionEpoch || snapshot.market!==s.selectedLiveMarket) return false;
    set({evidence:{snapshot,receivedAt,transitSeconds},observerInstanceId:snapshot.status.observer_instance_id,
      connectionGeneration:snapshot.status.connection_generation,latestStreamSequence:s.observerInstanceId===snapshot.status.observer_instance_id && s.connectionGeneration===snapshot.status.connection_generation?s.latestStreamSequence:0,lastValidatedAt:receivedAt,
      current:true,streamStatus:snapshot.status.connection_state==='DISABLED'?'DISABLED':'CONNECTING',connectionNotice:null});
    return true;
  },
  acceptFrame: (frame,epoch,receivedAt,transitSeconds) => {
    const s=get();
    if (epoch!==s.selectionEpoch || frame.market!==s.selectedLiveMarket || frame.observer_instance_id!==s.observerInstanceId || frame.connection_generation!==s.connectionGeneration || frame.sequence<=s.latestStreamSequence) return false;
    set({evidence:{snapshot:frame.payload,receivedAt,transitSeconds},latestStreamSequence:frame.sequence,
      lastValidatedAt:receivedAt,current:true,streamStatus:'CONNECTED',connectionNotice:null}); return true;
  },
  rejectFrame: (epoch,connectionNotice) => {
    if(epoch!==get().selectionEpoch)return;
    set(s=>({connectionNotice,rejectedFrames:Math.min(s.rejectedFrames+1,Number.MAX_SAFE_INTEGER)}));
  },
}));
