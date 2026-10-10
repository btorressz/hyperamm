import { create } from 'zustand';
import type { ResearchPreset, ResearchPreviewResponse, ResearchProposal, ResearchVaultConfig } from '../types';
import { useTerminalStore } from './terminal';
import { sessionCurrent } from '../utils/researchEvidence';
import { shiftDecimal } from '../utils/researchVault';
export type PreviewToken = { request: number; version: number; epoch: number; proposal: ResearchProposal };
type ResearchStore = {
  selectedPresetId: string | null; preset: ResearchPreset | null; draftConfig: ResearchVaultConfig | null;
  draftVersion: number; evidenceEpoch: number; requestVersion: number; preview: ResearchPreviewResponse | null;
  validatedVersion: number | null; lastValidatedConfig: ResearchVaultConfig | null; lastValidatedFingerprint: string | null;
  useForResearch: boolean; pending: boolean; error: string;
  utilizationPercentDraft: string;
  selectPreset: (preset: ResearchPreset) => void; edit: (patch: Partial<ResearchVaultConfig>) => void;
  reset: () => void; beginPreview: () => PreviewToken | null;
  editUtilizationPercent: (value: string) => void;
  acceptPreview: (token: PreviewToken, preview: ResearchPreviewResponse) => boolean;
  failPreview: (token: PreviewToken, message: string) => void; retireRequest: () => void;
  invalidateEvidence: () => void; choose: () => void;
};
export const useResearchVaultStore = create<ResearchStore>((set, get) => ({
  selectedPresetId: null, preset: null, draftConfig: null, draftVersion: 0, evidenceEpoch: 0, requestVersion: 0,
  preview: null, validatedVersion: null, lastValidatedConfig: null, lastValidatedFingerprint: null,
  useForResearch: false, pending: false, error: '', utilizationPercentDraft: '',
  selectPreset: preset => set(s => ({ preset: structuredClone(preset), selectedPresetId: preset.preset_id,
    draftConfig: {...preset.config}, utilizationPercentDraft: shiftDecimal(preset.config.max_capital_utilization, 2),
    draftVersion: s.draftVersion + 1, useForResearch: false, error: '' })),
  edit: patch => set(s => ({ draftConfig: s.draftConfig ? {...s.draftConfig, ...patch} : null,
    ...(patch.max_capital_utilization === undefined ? {} : {utilizationPercentDraft: shiftDecimal(patch.max_capital_utilization, 2)}),
    draftVersion: s.draftVersion + 1, useForResearch: false, error: '' })),
  editUtilizationPercent: value => {
    get().edit({max_capital_utilization: shiftDecimal(value, -2)});
    set({utilizationPercentDraft: value});
  },
  reset: () => { const p = get().preset; if (p) get().selectPreset(p); },
  beginPreview: () => {
    const s = get(); if (s.pending || !s.draftConfig) return null;
    const token = { request: s.requestVersion + 1, version: s.draftVersion, epoch: s.evidenceEpoch,
      proposal: { config: {...s.draftConfig}, selected_preset_id: s.selectedPresetId } };
    set({pending: true, requestVersion: token.request, validatedVersion: null, useForResearch: false, error: ''}); return token;
  },
  acceptPreview: (token, preview) => {
    const s = get(); if (s.requestVersion !== token.request) return false;
    set({pending: false});
    if (s.draftVersion !== token.version || s.evidenceEpoch !== token.epoch) return false;
    set({preview, validatedVersion: token.version, lastValidatedConfig: {...preview.normalized_config},
      lastValidatedFingerprint: preview.config_fingerprint, error: ''}); return true;
  },
  failPreview: (token, message) => {
    const s = get(); if (s.requestVersion === token.request) set({pending: false,
      error: s.draftVersion === token.version && s.evidenceEpoch === token.epoch ? message : ''});
  },
  retireRequest: () => set(s => ({pending: false, requestVersion: s.requestVersion + 1})),
  invalidateEvidence: () => set(s => ({evidenceEpoch: s.evidenceEpoch + 1, validatedVersion: null,
    useForResearch: false, pending: false, requestVersion: s.requestVersion + 1})),
  choose: () => { const s = get(); if (s.validatedVersion === s.draftVersion && s.lastValidatedConfig) set({useForResearch: true}); },
}));
// Synchronous invalidation handles batched disconnect/reconnect and session replacement.
useTerminalStore.subscribe((next, previous) => {
  if (next.wsState !== previous.wsState || next.terminal?.process_id !== previous.terminal?.process_id
    || next.terminal?.session_id !== previous.terminal?.session_id) useResearchVaultStore.getState().invalidateEvidence();
});
export function capturedResearch(): { proposal: ResearchProposal; baseline: ResearchProposal; fingerprint: string } | null {
  const s = useResearchVaultStore.getState();
  if (!s.useForResearch || s.validatedVersion !== s.draftVersion || !s.lastValidatedConfig || !s.preset || !s.lastValidatedFingerprint) return null;
  const terminal = useTerminalStore.getState();
  if (!terminal.terminal || !sessionCurrent(terminal.terminal, terminal)) {
    s.invalidateEvidence(); return null;
  }
  return { proposal: {config: {...s.lastValidatedConfig}, selected_preset_id: s.selectedPresetId},
    baseline: {config: {...s.preset.config}, selected_preset_id: s.selectedPresetId}, fingerprint: s.lastValidatedFingerprint };
}
