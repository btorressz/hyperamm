import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { paperProfileVersion } from '../../types/generalizedPaper';
import type { GeneralizedPaperResult, PaperAdmission, PaperProposal } from '../../types/generalizedPaper';
import { paperAdmissionIsCurrent } from '../../utils/generalizedPaper';
import { marketUniverseKey } from '../../utils/marketUniverse';
import { Panel } from '../TerminalPrimitives';

export function GeneralizedPaper({ scenarios }: { scenarios: readonly { name: string }[] }) {
  const discovery = useQuery({
    queryKey: ['generalized-paper-discovery'],
    queryFn: ({ signal }) => api.marketUniverse(signal),
    retry: false,
  });
  const [market, setMarket] = useState('');
  const [price, setPrice] = useState('');
  const [scenario, setScenario] = useState('QUIET');
  const [funding, setFunding] = useState(false);
  const [admission, setAdmission] = useState<PaperAdmission | null>(null);
  const [result, setResult] = useState<GeneralizedPaperResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [expired, setExpired] = useState(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    if (admission?.status !== 'ELIGIBLE') return;
    const timer = window.setTimeout(() => setExpired(true), Math.max(0, Date.parse(admission.valid_until) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [admission]);

  const records = discovery.data?.catalog?.records ?? [];
  const record = records.find(item => marketUniverseKey(item.identity) === market);
  const proposal: PaperProposal | null = record && price.trim() && scenarios.some(item => item.name === scenario) ? {
    profile_version: paperProfileVersion, identity: record.identity, simulated_reference_price: price.trim(),
    scenario, frames: 40, trace_max_points: 40,
    economics: { model: 'HYPOTHETICAL_LINEAR', funding_interval_seconds: funding ? 1 : null },
  } : null;
  const ready = discovery.data?.availability === 'AVAILABLE' && record?.listed === true &&
    !expired && paperAdmissionIsCurrent(admission);
  const reset = () => {
    setAdmission(null);
    setResult(null);
    setError('');
    setExpired(false);
  };

  async function submit(run: boolean) {
    if (pending.current || !proposal || (run && (!ready || admission?.status !== 'ELIGIBLE'))) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError('');
    if (!run) reset();
    try {
      const evidence = run && admission?.status === 'ELIGIBLE'
        ? await api.runGeneralizedPaper(proposal, admission.binding, controller.signal)
        : await api.paperEligibility(proposal, controller.signal);
      if (controller.signal.aborted) return;
      if ('status' in evidence) {
        setAdmission(evidence);
        setResult(null);
      } else {
        setResult(evidence);
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        setAdmission(null);
        setResult(null);
        setError(e instanceof Error ? e.message : 'The local PAPER request failed.');
      }
    } finally {
      pending.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <Panel title="Generalized PAPER research">
    <div className="stack">
      <p>Supply a hypothetical reference price for one discovered Core or HIP-3 perpetual. This local simulation uses synthetic prices and liquidity, with zero modeled fees. Venue fees, funding, collateral and margin are unverified. Discovery and PAPER admission grant no trading authority.</p>
      <div className="researchControls">
        <label>Discovered perpetual
          <select value={market} disabled={busy || records.length === 0}
            onChange={e => { setMarket(e.target.value); reset(); }}>
            <option value="">Select a perpetual</option>
            {records.map(item => <option key={marketUniverseKey(item.identity)} value={marketUniverseKey(item.identity)}>
              {item.source_coin} · {item.identity.instrument_type === 'HIP3_PERP' ? 'HIP-3' : 'Core'}
              {item.listed ? '' : ' · Delisted'}
            </option>)}
          </select>
        </label>
        <button type="button" disabled={busy || discovery.isFetching} onClick={() => { reset(); void discovery.refetch(); }}>
          Refresh discovery
        </button>
      </div>
      <p role="status">{discovery.isFetching ? 'Loading read-only discovery metadata…' : discovery.isError ?
        'Discovery could not be loaded.' : discovery.data?.availability === 'AVAILABLE' ?
        `${discovery.data.network} metadata available. Check PAPER eligibility for your scenario.` :
        `Discovery ${discovery.data?.availability.toLowerCase() ?? 'unavailable'}.`}</p>
      <div className="researchControls">
        <label>Synthetic reference price
          <input value={price} inputMode="decimal" maxLength={24} disabled={busy}
            onChange={e => { setPrice(e.target.value); reset(); }} />
        </label>
        <label>PAPER scenario
          <select value={scenario} disabled={busy} onChange={e => { setScenario(e.target.value); reset(); }}>
            {scenarios.map(item => <option key={item.name} value={item.name}>{item.name.replaceAll('_', ' ')}</option>)}
          </select>
        </label>
        <label><input type="checkbox" checked={funding} disabled={busy} onChange={e => { setFunding(e.target.checked); reset(); }} />
          Apply hypothetical funding at each one-second interval
        </label>
      </div>
      <div className="researchControls">
        <button type="button" disabled={!proposal || busy || discovery.isFetching} onClick={() => void submit(false)}>Check PAPER eligibility</button>
        <button type="button" disabled={!proposal || !ready || busy || discovery.isFetching} onClick={() => void submit(true)}>Run local PAPER</button>
      </div>
      {error && <p role="alert">{error}</p>}
      {admission && <div role="status">
        <p>{admission.status === 'ELIGIBLE' && !ready ? 'PAPER eligibility expired. Check eligibility again.' : admission.explanation}</p>
        {admission.status !== 'ELIGIBLE' && <p><code>{admission.reason}</code> · {admission.checks.join(', ').replaceAll('_', ' ')}</p>}
      </div>}
      {result && <div role="status">
        <p>Simulated PAPER result for {result.admission.profile.exchange_coin} · {result.result.metrics.frame_count} frames · {result.result.metrics.fill_count} fills</p>
        <dl>
          <dt>Net P&amp;L in hypothetical quote units</dt><dd>{result.result.vault.net_pnl_quote}</dd>
          <dt>Fees in hypothetical quote units</dt><dd>{result.result.vault.fees_quote}</dd>
          <dt>Funding in hypothetical quote units</dt><dd>{result.result.vault.funding_quote}</dd>
          <dt>Inventory in base units</dt><dd>{result.result.vault.position_base}</dd>
        </dl>
        <details><summary>Result fingerprint</summary><p className="break-word">{result.result_fingerprint}</p></details>
      </div>}
    </div>
  </Panel>;
}
