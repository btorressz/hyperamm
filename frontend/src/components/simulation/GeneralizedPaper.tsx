import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { paperProfileVersion } from '../../types/generalizedPaper';
import type { GeneralizedPaperResult, PaperAdmission, PaperProposal } from '../../types/generalizedPaper';
import { paperAdmissionIsCurrent } from '../../utils/generalizedPaper';
import { marketUniverseKey } from '../../utils/marketUniverse';
import { buildRiskSettings, financialEvidenceIsCurrent } from '../../utils/marketRisk';
import { accountingValue } from '../../utils/researchEvidence';
import { Panel } from '../TerminalPrimitives';
import { initialRiskDraft, PaperFinancialEvidence, PaperRiskConfiguration, PaperRiskEvidence } from './GeneralizedPaperRisk';

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
  const [riskDraft, setRiskDraft] = useState(initialRiskDraft);
  const [admission, setAdmission] = useState<PaperAdmission | null>(null);
  const [result, setResult] = useState<GeneralizedPaperResult | null>(null);
  const [error, setError] = useState('');
  const [working, setWorking] = useState<'checking' | 'running' | null>(null);
  const [expired, setExpired] = useState(false);
  const [expiredFinancialDeadline, setExpiredFinancialDeadline] = useState('');
  const pending = useRef<AbortController | null>(null);
  const { data: catalog, isError: discoveryFailed, isFetching } = discovery;
  const catalogFingerprint = catalog?.catalog_fingerprint;
  const catalogNetwork = catalog?.network;
  const availability = catalog?.availability;
  const busy = working !== null;
  const riskEnabled = riskDraft.mode !== 'OFF';
  const records = catalog?.catalog?.records ?? [];
  const recordIndex = records.findIndex(item => marketUniverseKey(item.identity) === market);
  const record = records[recordIndex];
  const discoveryDecision = catalog?.eligibility[recordIndex];
  const selection = record && discoveryDecision && catalogFingerprint && availability === 'AVAILABLE' && !discoveryFailed
    ? { metadata: record, metadata_fingerprint: discoveryDecision.metadata_fingerprint,
      catalog_fingerprint: catalogFingerprint, max_age_seconds: catalog.max_age_seconds } : null;
  const financialQuery = useQuery({
    queryKey: ['generalized-paper-financial', market, catalogFingerprint],
    queryFn: ({ signal }) => {
      if (!selection) throw new Error('Select a market from the current discovery catalog.');
      return api.marketRiskEvidence(selection, signal);
    },
    enabled: selection !== null,
    retry: false,
  });
  const financial = selection && !financialQuery.isError ? financialQuery.data : undefined;
  const financialExpired = financial !== undefined &&
    (financial.valid_until === expiredFinancialDeadline || !financialEvidenceIsCurrent(financial));
  const currentFinancial = financial !== undefined && !financialExpired;
  const financialGeneration = riskEnabled && financial
    ? `${financial.source_fingerprint ?? ''}:${financial.valid_until}:${financialExpired}` : '';

  function reset() {
    pending.current?.abort();
    pending.current = null;
    setWorking(null);
    setAdmission(null);
    setResult(null);
    setError('');
    setExpired(false);
  }

  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    reset();
  }, [catalogFingerprint, catalogNetwork, availability, discoveryFailed, financialGeneration]);
  useEffect(() => {
    if (admission?.status !== 'ELIGIBLE') return;
    const timer = window.setTimeout(() => {
      setExpired(true);
      if (admission.risk_model) {
        pending.current?.abort();
        pending.current = null;
        setWorking(null);
        setResult(null);
      }
    }, Math.max(0, Date.parse(admission.valid_until) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [admission]);
  useEffect(() => {
    if (!financial) return;
    const deadline = financial.valid_until;
    const timer = window.setTimeout(() => setExpiredFinancialDeadline(deadline), Math.max(0, Date.parse(deadline) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [financial]);

  let riskSettings: PaperProposal['research_risk'];
  let riskError = '';
  if (riskDraft.mode !== 'OFF') {
    try {
      riskSettings = buildRiskSettings(riskDraft.mode, riskDraft.marginMode, riskDraft.capital, riskDraft.initial,
        riskDraft.maintenance, riskDraft.leverage, riskDraft.ceiling, riskDraft.rate, riskDraft.stresses,
        currentFinancial ? financial : undefined);
    } catch (e) {
      riskError = e instanceof Error ? e.message : 'Check the research risk settings.';
    }
  }
  const proposal: PaperProposal | null = record && price.trim() && !riskError && scenarios.some(item => item.name === scenario) ? {
    profile_version: paperProfileVersion, identity: record.identity, simulated_reference_price: price.trim(),
    scenario, frames: 40, trace_max_points: 40,
    economics: { model: 'HYPOTHETICAL_LINEAR', funding_interval_seconds: funding ? 1 : null },
    ...(riskSettings ? { research_risk: riskSettings } : {}),
  } : null;
  const financialMatches = (evidence: PaperAdmission) =>
    !riskEnabled || evidence.status !== 'ELIGIBLE' || !currentFinancial ||
    (evidence.risk_model?.source_fingerprint ?? null) === financial?.source_fingerprint;
  const catalogMatches = admission?.status === 'ELIGIBLE' && !discoveryFailed &&
    availability === 'AVAILABLE' && admission.binding.catalog_fingerprint === catalogFingerprint &&
    admission.binding.metadata_fingerprint === discoveryDecision?.metadata_fingerprint &&
    admission.identity?.network === catalogNetwork && financialMatches(admission);
  const financialPending = riskEnabled && financialQuery.isFetching;
  const ready = catalogMatches && record?.listed === true &&
    !isFetching && !financialPending && !expired && paperAdmissionIsCurrent(admission);

  async function submit(run: boolean) {
    if (pending.current || !proposal || isFetching || financialPending ||
        (run && (!ready || !paperAdmissionIsCurrent(admission) || admission?.status !== 'ELIGIBLE'))) return;
    if (proposal.research_risk?.mode === 'SOURCE_CONSTRAINED' && !financialEvidenceIsCurrent(financial)) return;
    if (!run) reset();
    const controller = new AbortController();
    pending.current = controller;
    setWorking(run ? 'running' : 'checking');
    setResult(null);
    setError('');
    try {
      const evidence = run && admission?.status === 'ELIGIBLE'
        ? await api.runGeneralizedPaper(proposal, admission.binding, controller.signal)
        : await api.paperEligibility(proposal, controller.signal);
      if (controller.signal.aborted) return;
      const decision = 'status' in evidence ? evidence : evidence.admission;
      if (decision.status === 'ELIGIBLE' && (decision.binding.catalog_fingerprint !== catalogFingerprint ||
          decision.binding.metadata_fingerprint !== discoveryDecision?.metadata_fingerprint || !financialMatches(decision)))
        throw new Error('Discovery or financial evidence changed. Refresh discovery and check eligibility again.');
      if (riskEnabled && !('status' in evidence) && !paperAdmissionIsCurrent(decision)) {
        setExpired(true);
        return;
      }
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
      if (pending.current === controller) {
        pending.current = null;
        setWorking(null);
      }
    }
  }

  return <Panel title="Generalized PAPER research">
    <div className="researchInset stack">
      <p>Supply a hypothetical reference price for one discovered Core or HIP-3 perpetual. This local simulation uses synthetic prices and liquidity, with zero modeled fees. Venue fees, funding, account balances and actual margin requirements are unverified. Discovery and PAPER admission grant no trading authority.</p>
      <div className="researchFilters">
        <label>Discovered perpetual
          <select value={record ? market : ''} disabled={busy || records.length === 0}
            onChange={e => {
              reset();
              setMarket(e.target.value);
              setRiskDraft(draft => ({ ...draft, marginMode: 'ISOLATED', rate: '' }));
            }}>
            <option value="">Select a perpetual</option>
            {records.map(item => <option key={marketUniverseKey(item.identity)} value={marketUniverseKey(item.identity)}>
              {item.source_coin} · {item.identity.instrument_type === 'HIP3_PERP' ? 'HIP-3' : 'Core'}
              {item.listed ? '' : ' · Delisted'}
            </option>)}
          </select>
        </label>
        <button type="button" disabled={busy || isFetching} onClick={() => {
          reset();
          void discovery.refetch().then(next => {
            if (selection && next.data?.catalog_fingerprint === selection.catalog_fingerprint && next.data.availability === 'AVAILABLE')
              void financialQuery.refetch();
          });
        }}>
          Refresh discovery
        </button>
      </div>
      <p role={discoveryFailed ? 'alert' : 'status'}>{isFetching ? 'Loading read-only discovery metadata…' : discoveryFailed ?
        'Discovery could not be loaded.' : availability === 'AVAILABLE' ?
        `${catalogNetwork} metadata available. Check PAPER eligibility for your scenario.` :
        `Discovery ${availability?.toLowerCase() ?? 'unavailable'}.`}</p>
      {record && <dl className="researchDetails">
        <div><dt>Canonical market</dt><dd><code>{marketUniverseKey(record.identity)}</code></dd></div>
        <div><dt>Instrument</dt><dd>{record.source_coin} · {record.identity.instrument_type === 'HIP3_PERP' ? 'HIP-3' : 'Core'}</dd></div>
        <div><dt>Network and DEX</dt><dd>{record.identity.network} · {record.identity.dex || 'Core (default namespace)'}</dd></div>
        <div><dt>Discovery status</dt><dd>{discoveryDecision?.reason.replaceAll('_', ' ') ?? 'Unavailable'}</dd></div>
        <div><dt>Research profile version</dt><dd>{paperProfileVersion}</dd></div>
        <div><dt>Exchange metadata observed at</dt><dd><time dateTime={record.observed_at}>{record.observed_at}</time></dd></div>
        <div><dt>Metadata freshness</dt><dd>{record.metadata_status === 'STALE' || availability !== 'AVAILABLE' || discoveryFailed
          ? 'Stale or unavailable' : 'Available at last discovery'}</dd></div>
      </dl>}
      {record && <PaperFinancialEvidence evidence={financial} current={currentFinancial}
        loading={selection !== null && financialQuery.isFetching} error={financialQuery.error?.message} />}
      <div className="researchFilters">
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
      <PaperRiskConfiguration draft={riskDraft} evidence={financial} current={currentFinancial}
        error={riskError} onChange={next => { reset(); setRiskDraft(next); }} />
      <div className="researchFilters">
        <button type="button" disabled={!proposal || busy || isFetching || financialPending || discoveryFailed} onClick={() => void submit(false)}>Check PAPER eligibility</button>
        <button type="button" disabled={!proposal || !ready || busy} onClick={() => void submit(true)}>Run local PAPER</button>
      </div>
      {working && <p role="status">{working === 'running' ? 'Running local PAPER simulation…' : 'Checking PAPER eligibility…'}</p>}
      {error && <p role="alert">{error}</p>}
      {admission && <div role="status">
        {admission.status === 'ELIGIBLE' ? <>
          <p>{!catalogMatches ? 'Discovery evidence changed. Refresh discovery and check eligibility again.' :
            expired || !paperAdmissionIsCurrent(admission)
              ? 'PAPER eligibility expired. Check eligibility again.' : admission.explanation}</p>
          {ready && <p>Eligibility valid until <time dateTime={admission.valid_until}>{admission.valid_until}</time></p>}
        </> : <p>{admission.explanation}</p>}
        {admission.status !== 'ELIGIBLE' && <p><code>{admission.reason}</code> · {admission.checks.join(', ').replaceAll('_', ' ')}</p>}
      </div>}
      {result && catalogMatches && (!riskEnabled || (!expired && paperAdmissionIsCurrent(admission))) &&
        <PaperResult result={result} />}
    </div>
  </Panel>;
}

function PaperResult({ result }: { result: GeneralizedPaperResult }) {
  const { profile } = result.admission;
  const { economics } = profile;
  const { metrics, vault } = result.result;
  const fields = [
    ['Starting simulated equity', vault.initial_equity_quote],
    ['Ending simulated equity', vault.equity_quote],
    ['Net P&L in hypothetical quote units', vault.net_pnl_quote],
    ['Realized trading P&L', vault.realized_pnl_quote],
    ['Unrealized trading P&L', vault.unrealized_pnl_quote],
    ['Fees in hypothetical quote units', vault.fees_quote],
    ['Funding in hypothetical quote units', vault.funding_quote],
    ['Simulated full-notional reservation', vault.reserved_capital_quote],
    ['Inventory in base units', vault.position_base],
  ];
  return <section aria-label="PAPER result evidence">
    <p role="status">Simulated PAPER result for {profile.exchange_coin} · {metrics.frame_count} frames · {metrics.fill_count} fills</p>
    <p>Synthetic reference input {accountingValue(profile.simulated_reference_price)} · Synthetic top depth {accountingValue(profile.synthetic_top_depth_quote)} hypothetical quote units.</p>
    <p>Modeled maker fee {accountingValue(economics.maker_fee_bps)} bps · Modeled taker fee {accountingValue(economics.taker_fee_bps)} bps.
      {' '}{economics.funding_interval_seconds === null ? 'Hypothetical funding disabled.' :
        `Hypothetical funding interval ${economics.funding_interval_seconds} s.`}</p>
    <p>Equity, P&amp;L, fees, funding and reservation use hypothetical quote units. Inventory is simulated.
      {' '}{result.research_risk ? 'Public market observations and modeled risk are shown below.' :
        'Exchange collateral, margin, liquidation, leverage, settlement and account balances are unverified.'}</p>
    <dl className="researchDetails">
      {fields.map(([label, amount]) => <div key={label}><dt>{label}</dt><dd>{accountingValue(amount)}</dd></div>)}
    </dl>
    {result.research_risk && result.admission.risk_model && result.admission.risk_source_status &&
      <PaperRiskEvidence risk={result.research_risk} model={result.admission.risk_model}
        sourceStatus={result.admission.risk_source_status} />}
    <details>
      <summary>Result fingerprint and provenance</summary>
      <p>Simulation started at <time dateTime={result.started_at}>{result.started_at}</time> with current exchange metadata.
        Reference confidence and timestamps describe the synthetic scenario.</p>
      <p><code>{result.result_fingerprint}</code></p>
    </details>
  </section>;
}
