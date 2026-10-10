import { create } from 'zustand';
import type { ResearchMarketCatalog, ResearchMarketId, ResearchMarketProfile } from '../types';
import { useTerminalStore } from './terminal';
import { useResearchVaultStore } from './researchVault';
import { researchMarketIds, checkedMarketCatalog } from '../utils/researchMarkets';

type MarketStore = {
  selectedResearchMarket: ResearchMarketId; marketCatalogVersion: string | null;
  marketProfileFingerprint: string | null; marketSelectionVersion: number; evidenceEpoch: number;
  catalog: ResearchMarketCatalog | null;
  selectMarket: (market: ResearchMarketId) => void;
  acceptCatalog: (catalog: ResearchMarketCatalog, epoch: number) => boolean;
  invalidate: () => void;
};
export const useResearchMarketStore = create<MarketStore>((set, get) => ({
  selectedResearchMarket: 'ETH', marketCatalogVersion: null, marketProfileFingerprint: null,
  marketSelectionVersion: 0, evidenceEpoch: 0, catalog: null,
  selectMarket: market => {
    if (!researchMarketIds.includes(market)) throw new Error('Unsupported research market');
    if (market === get().selectedResearchMarket) return;
    set(s => ({selectedResearchMarket: market, marketSelectionVersion: s.marketSelectionVersion + 1,
      marketProfileFingerprint: s.catalog?.markets.find(p => p.market === market)?.profile_fingerprint ?? null}));
    useResearchVaultStore.getState().invalidateEvidence();
  },
  acceptCatalog: (catalog, epoch) => {
    checkedMarketCatalog(catalog);
    const s = get(); if (s.evidenceEpoch !== epoch) return false;
    const selected = catalog.markets.find(p => p.market === s.selectedResearchMarket)!;
    if (s.marketProfileFingerprint && s.marketProfileFingerprint !== selected.profile_fingerprint)
      useResearchVaultStore.getState().invalidateEvidence();
    set({catalog: structuredClone(catalog), marketCatalogVersion: catalog.catalog_version,
      marketProfileFingerprint: selected.profile_fingerprint}); return true;
  },
  invalidate: () => set(s => ({catalog: null, marketCatalogVersion: null, marketProfileFingerprint: null,
    evidenceEpoch: s.evidenceEpoch + 1, marketSelectionVersion: s.marketSelectionVersion + 1})),
}));
useTerminalStore.subscribe((next, previous) => {
  if (next.wsState !== previous.wsState || next.terminal?.process_id !== previous.terminal?.process_id
      || next.terminal?.session_id !== previous.terminal?.session_id) useResearchMarketStore.getState().invalidate();
});
export function capturedMarket(): ResearchMarketProfile | null {
  const s = useResearchMarketStore.getState();
  const p = s.catalog?.markets.find(p => p.market === s.selectedResearchMarket);
  return p?.research_supported ? structuredClone(p) : null;
}
