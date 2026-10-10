import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { TerminalState } from '../../types';
import { api } from '../../api/client';
import { useResearchSession } from '../../hooks/useResearchSession';
import { useResearchVaultStore } from '../../stores/researchVault';
import { checkedCatalog, checkedPreview } from '../../utils/researchVault';
import { Panel, StatusBanner } from '../TerminalPrimitives';
import { Badge } from '../Badge';
import { ResearchPresets } from './ResearchPresets';
import { ResearchPreview } from './ResearchPreview';
import '../../phase14.css';
export function ResearchConfiguration({t, historical}: {t: TerminalState; historical: boolean}) {
  const session = useResearchSession(t, historical), s = useResearchVaultStore();
  const controller = useRef<AbortController | null>(null);
  const catalog = useQuery({queryKey: ['research-vault-presets'],
    queryFn: async ({signal}) => checkedCatalog(await api.researchPresets(signal)),
    retry: false, refetchOnWindowFocus: false});
  useEffect(() => {
    if (!useResearchVaultStore.getState().draftConfig && catalog.data) {
      s.selectPreset(catalog.data.presets.find(p => p.preset_id === 'balanced-research') ?? catalog.data.presets[0]);
    }
  }, [catalog.data, s.selectPreset]);
  useEffect(() => () => { controller.current?.abort(); useResearchVaultStore.getState().retireRequest(); }, []);
  const validate = async () => {
    const token = s.beginPreview(); if (!token) return;
    const abort = new AbortController(); controller.current = abort;
    try {
      session.check();
      const response = checkedPreview(await api.researchPreview(token.proposal, abort.signal), token.proposal);
      session.check();
      useResearchVaultStore.getState().acceptPreview(token, response);
    } catch (e) {
      useResearchVaultStore.getState().failPreview(token, e instanceof Error ? e.message : 'Research preview unavailable.');
    }
  };
  const d = s.draftConfig, current = s.validatedVersion === s.draftVersion && session.enabled;
  return <section className="researchStudio stack" aria-label="Research Configuration Studio">
    <div className="researchPageTitle"><h2>Research Configuration Studio</h2><Badge tone="blue">PAPER RESEARCH ONLY</Badge></div>
    <StatusBanner>HYPOTHETICAL ACCOUNTING ASSUMPTIONS · NO LIVE TRADING AUTHORITY. Local drafts do not change Vault capital, active strategy, risk limits or orders.</StatusBanner>
    <Panel title="Preset library" meta="PYTHON-OWNED · VERSIONED">
      {catalog.isPending && <p role="status">Loading research presets…</p>}
      {catalog.isError && <p className="inlineError" role="alert">{catalog.error.message} <button onClick={() => void catalog.refetch()}>Retry presets</button></p>}
      {catalog.data && <ResearchPresets presets={catalog.data.presets} selected={s.selectedPresetId} onSelect={s.selectPreset}/>}
    </Panel>
    {d && <Panel title="Edit local research draft" meta={`DRAFT v${s.draftVersion}`}>
      <p>Selected preset: {s.preset?.name} · {current ? 'Last validated draft is current' : 'Draft requires validation'} · {s.useForResearch ? 'Selected for PAPER research' : 'Not selected for PAPER research'}</p>
      <div className="formGrid">
        <label>Simulated starting capital (quote)<input inputMode="decimal" value={d.initial_equity_quote} maxLength={80} onChange={e => s.edit({initial_equity_quote: e.target.value})}/></label>
        <label>Maker fee (bps)<input inputMode="decimal" value={d.paper_maker_fee_bps} maxLength={80} onChange={e => s.edit({paper_maker_fee_bps: e.target.value})}/></label>
        <label>Taker fee (bps)<input inputMode="decimal" value={d.paper_taker_fee_bps} maxLength={80} onChange={e => s.edit({paper_taker_fee_bps: e.target.value})}/></label>
        <label>Capital utilization limit (%)<input inputMode="decimal" value={s.utilizationPercentDraft} maxLength={80} onChange={e => s.editUtilizationPercent(e.target.value)}/></label>
        <label>Funding interval (seconds)<select aria-label="Funding interval (seconds)" value={d.paper_funding_interval_seconds} onChange={e => s.edit({paper_funding_interval_seconds: Number(e.target.value)})}>{[1,60,300,3600,28800,86400].map(i => <option key={i} value={i}>{i} seconds</option>)}</select></label>
        <label className="researchToggle"><input type="checkbox" checked={d.paper_fee_model_enabled} onChange={e => s.edit({paper_fee_model_enabled: e.target.checked})}/>Simulated fee model enabled</label>
        <label className="researchToggle"><input type="checkbox" checked={d.paper_funding_accounting_enabled} onChange={e => s.edit({paper_funding_accounting_enabled: e.target.checked})}/>Simulated funding accounting enabled</label>
      </div>
      <p className="muted">Capital: greater than zero, at most 1 trillion quote. Fees: 0–100 bps. Utilization: greater than 0%, at most 100%. Decimal inputs support up to 18 fractional places. Python validation is authoritative.</p>
      <div className="actions">
        <button className="primary" disabled={s.pending || !session.enabled} onClick={() => void validate()}>{s.pending ? 'Validating…' : 'Validate / Preview'}</button>
        <button onClick={s.reset}>Reset to selected preset</button>
        <button disabled={!current || s.pending} onClick={s.choose}>Use configuration for PAPER research</button>
        {s.useForResearch && <a href="#/simulation">Open Simulation</a>}
      </div>
      {!session.enabled && <p role="status">Current backend session unavailable. Draft remains local; reconnect and revalidate.</p>}
      {s.error && <p className="inlineError" role="alert">{s.error}</p>}
    </Panel>}
    {s.preview && <ResearchPreview preview={s.preview} current={current}/>}
  </section>;
}
