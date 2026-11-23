import { ObservedMarketSummary } from '../markets/ObservedMarketSummary';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { assetPaperReasonText, paperProfileVersion } from '../../types/generalizedPaper';
import type { AdvisoryResponse } from '../../types/advisory';
import type { AssetAmmResearchPolicy, AssetControlInputs, AssetPolicyPreviewRequest } from '../../types/assetAmm';
import type { GeneralizedPaperResult, PaperAdmission, PaperProposal } from '../../types/generalizedPaper';
import { assetControlInput, assetMinimumNotional, assetReferenceIsValid } from '../../utils/assetAmm';
import { paperAdmissionIsCurrent } from '../../utils/generalizedPaper';
import { generalizedDiscoveryQuery, useGeneralizedMarketSelection } from '../../stores/researchMarkets';
import { pageHref } from '../../utils/navigation';
import { useDisplayStore } from '../../stores/display';
import { useTerminalStore } from '../../stores/terminal';
import { GuidedPaperStep, guidedPaperScenarios } from './GuidedPaperResearch';
import { marketCatalogDeadline, marketUniverseKey, matchesMarketResearchHandoff } from '../../utils/marketUniverse';
import { buildRiskSettings, financialEvidenceIsCurrent } from '../../utils/marketRisk';
import { accountingValue } from '../../utils/researchEvidence';
import { Panel } from '../TerminalPrimitives';
import { GeneralizedPaperAdvisory } from './GeneralizedPaperAdvisory';
import { initialAssetDraft, PaperAssetConfiguration, PaperAssetEvidence } from './GeneralizedPaperAssetPolicy';
import { initialRiskDraft, PaperFinancialEvidence, PaperRiskConfiguration, PaperRiskEvidence } from './GeneralizedPaperRisk';

type CompletedPaper = {
  readonly evidence: GeneralizedPaperResult;
  readonly receivedAt: string;
};

export function GeneralizedPaper({ scenarios, resultsOnly, active }: {
  scenarios: readonly { name: string; description: string }[];
  resultsOnly: boolean;
  active: boolean;
}) {
  const guided = useDisplayStore(state => state.experienceMode) === 'Starter';
  const setMode = useDisplayStore(state => state.setExperienceMode);
  const discovery = useQuery(generalizedDiscoveryQuery);
  const queryClient = useQueryClient();
  const handoff = useGeneralizedMarketSelection(state => state.handoff);
  const appliedHandoff = useRef<typeof handoff>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [handoffError, setHandoffError] = useState(false);
  const advanced = !guided || showAdvanced;
  const [market, setMarket] = useState('');
  const [price, setPrice] = useState('');
  const [scenario, setScenario] = useState('QUIET');
  const [funding, setFunding] = useState(false);
  const [assetEnabled, setAssetEnabled] = useState(false);
  const [assetDraft, setAssetDraft] = useState(initialAssetDraft);
  const [assetPolicy, setAssetPolicy] = useState<AssetAmmResearchPolicy | null>(null);
  const [assetAdvisory, setAssetAdvisory] = useState<AdvisoryResponse | null>(null);
  const [assetRunStarted, setAssetRunStarted] = useState(false);
  const [expiredCatalogDeadline, setExpiredCatalogDeadline] = useState(0);
  const [riskDraft, setRiskDraft] = useState(initialRiskDraft);
  const [admission, setAdmission] = useState<PaperAdmission | null>(null);
  const [completed, setCompleted] = useState<CompletedPaper | null>(null);
  const [error, setError] = useState('');
  const [working, setWorking] = useState<'checking' | 'running' | null>(null);
  const [advisoryEpoch, setAdvisoryEpoch] = useState(0);
  const [expired, setExpired] = useState(false);
  const [expiredFinancialDeadline, setExpiredFinancialDeadline] = useState('');
  const pending = useRef<{ controller: AbortController; run: boolean } | null>(null);
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
    queryKey: ['generalized-paper-financial', market, catalogFingerprint, discoveryDecision?.metadata_fingerprint],
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
  const catalogDeadline = marketCatalogDeadline(catalog);
  const catalogCurrent = availability === 'AVAILABLE' && !discoveryFailed &&
    catalogDeadline > Date.now() && catalogDeadline !== expiredCatalogDeadline;
  const assetSelectionCurrent = catalogCurrent &&
    discoveryDecision?.discovery_eligible === true;
  const currentAssetAdvisory = assetEnabled && assetSelectionCurrent && assetAdvisory &&
    assetAdvisory.snapshot.context.catalog_fingerprint === catalogFingerprint &&
    assetAdvisory.snapshot.context.metadata_fingerprint === discoveryDecision?.metadata_fingerprint &&
    Date.now() < Date.parse(assetAdvisory.valid_until) ? assetAdvisory : null;

  function resetAdmission(keepRunning = false) {
    setAdvisoryEpoch(epoch => epoch + 1);
    if (!keepRunning || !pending.current?.run) {
      pending.current?.controller.abort();
      pending.current = null;
      setWorking(null);
    }
    setAdmission(null);
    setAssetPolicy(null);
    setAssetRunStarted(false);
    setError('');
    setExpired(false);
  }

  function changeMarket(key: string) {
    resetAdmission();
    setHandoffError(false);
    setAssetAdvisory(null);
    setMarket(key);
    setRiskDraft(draft => ({ ...draft, marginMode: 'ISOLATED', rate: '' }));
  }

  useLayoutEffect(() => {
    if (!handoff || handoff === appliedHandoff.current || isFetching) return;
    appliedHandoff.current = handoff;
    if (!discoveryFailed && matchesMarketResearchHandoff(catalog, handoff)) {
      if (market !== handoff.key) {
        if (market) setPrice('');
        changeMarket(handoff.key);
      }
    } else {
      changeMarket('');
      setHandoffError(true);
    }
  }, [handoff, catalog, isFetching, discoveryFailed, market]);

  useEffect(() => {
    const unsubscribe = useTerminalStore.subscribe(({ terminal }, { terminal: prior }) => {
      if (terminal && prior && (terminal.process_id !== prior.process_id || terminal.session_id !== prior.session_id)) {
        resetAdmission();
        setAssetAdvisory(null);
      }
    });
    return () => {
      unsubscribe();
      pending.current?.controller.abort();
    };
  }, []);
  useLayoutEffect(() => {
    resetAdmission();
    setAssetAdvisory(null);
  }, [catalogFingerprint, catalogNetwork, discoveryDecision?.metadata_fingerprint]);
  useEffect(() => {
    resetAdmission(true);
    setAssetAdvisory(null);
  }, [availability, discoveryFailed]);
  useEffect(() => {
    resetAdmission(true);
  }, [financialGeneration]);
  useEffect(() => {
    if (!catalogDeadline) return;
    const timer = window.setTimeout(() => {
      resetAdmission(true);
      setAssetAdvisory(null);
      setExpiredCatalogDeadline(catalogDeadline);
      setError('Discovery evidence expired. PAPER eligibility expired. Refresh discovery and check again.');
    }, Math.max(0, catalogDeadline - Date.now()));
    return () => window.clearTimeout(timer);
  }, [catalogDeadline, catalogFingerprint]);
  useEffect(() => {
    if (!assetAdvisory) return;
    const timer = window.setTimeout(() => {
      resetAdmission(true);
      setError('Advisory evidence expired. Refresh or remove it before checking eligibility.');
    }, Math.max(0, Date.parse(assetAdvisory.valid_until) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [assetAdvisory]);
  useEffect(() => {
    if (admission?.status !== 'ELIGIBLE') return;
    const timer = window.setTimeout(() => {
      setExpired(true);
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
  const baseProposal: PaperProposal | null = record && price.trim() && !riskError && scenarios.some(item => item.name === scenario) ? {
    profile_version: paperProfileVersion, identity: record.identity, simulated_reference_price: price.trim(),
    scenario, frames: 40, trace_max_points: 40,
    economics: { model: 'HYPOTHETICAL_LINEAR', funding_interval_seconds: funding ? 1 : null },
    ...(riskSettings ? { research_risk: riskSettings } : {}),
  } : null;
  let assetError = '';
  let defaultRequest: AssetPolicyPreviewRequest | undefined;
  let assetRequest: AssetPolicyPreviewRequest | undefined;
  if (assetEnabled) {
    try {
      const minimum = assetMinimumNotional(assetDraft.minimum.trim());
      const reference = price.trim();
      if (reference && !assetReferenceIsValid(reference))
        throw new Error('Enter a positive exact synthetic reference price up to 10000000, with up to 12 decimal places.');
      if (selection && assetSelectionCurrent && reference) {
        defaultRequest = {
          profile_version: paperProfileVersion, identity: selection.metadata.identity,
          catalog_fingerprint: selection.catalog_fingerprint, simulated_reference_price: reference,
          minimum_order_notional: minimum, family: 'UNKNOWN',
        };
        const controls = Object.fromEntries(Object.entries(assetDraft.overrides).map(([key, value]) =>
          [key, assetControlInput(key as keyof AssetControlInputs, value.trim())]));
        assetRequest = {
          ...defaultRequest, family: assetDraft.family, controls,
          ...(riskSettings ? { research_risk: riskSettings } : {}),
          ...(currentAssetAdvisory ? { advisory_snapshot_fingerprint: currentAssetAdvisory.snapshot_fingerprint } : {}),
        };
      }
    } catch (e) {
      assetError = e instanceof Error ? e.message : 'Check the AMM research settings.';
    }
  }
  const defaults = useQuery({
    queryKey: ['generalized-paper-asset-defaults', defaultRequest],
    queryFn: ({ signal }) => {
      if (!selection || !defaultRequest) throw new Error('Select a market and enter a synthetic reference price.');
      return api.assetPolicyPreview(defaultRequest, selection, signal);
    },
    enabled: defaultRequest !== undefined && !isFetching,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    gcTime: 0,
  });
  const proposal = !assetEnabled ? baseProposal :
    baseProposal && assetPolicy && assetRequest ? {
      ...baseProposal, minimum_order_notional: assetRequest.minimum_order_notional, asset_amm_policy: assetPolicy,
    } : null;
  const financialMatches = (evidence: PaperAdmission) => {
    if (!riskEnabled || evidence.status !== 'ELIGIBLE') return true;
    const boundSource = evidence.risk_model?.source_fingerprint ?? null;
    return boundSource === (currentFinancial ? financial.source_fingerprint : null);
  };
  const catalogMatches = admission?.status === 'ELIGIBLE' && catalogCurrent &&
    admission.binding.catalog_fingerprint === catalogFingerprint &&
    admission.binding.metadata_fingerprint === discoveryDecision?.metadata_fingerprint &&
    admission.identity?.network === catalogNetwork && financialMatches(admission);
  const financialPending = riskEnabled && financialQuery.isFetching;
  const ready = catalogMatches && record?.listed === true && (!assetEnabled ||
    (assetSelectionCurrent && !!assetPolicy && !assetRunStarted && (!assetAdvisory || !!currentAssetAdvisory))) &&
    !isFetching && !financialPending && !expired && paperAdmissionIsCurrent(admission);

  async function submit(run: boolean) {
    if (pending.current || !baseProposal || isFetching || financialPending || !catalogCurrent || Date.now() >= catalogDeadline ||
        (assetEnabled && (!assetRequest || !selection || !assetSelectionCurrent ||
          (assetAdvisory && (!currentAssetAdvisory || Date.now() >= Date.parse(assetAdvisory.valid_until))))) ||
        (run && (!ready || !paperAdmissionIsCurrent(admission) || admission?.status !== 'ELIGIBLE'))) return;
    if (baseProposal.research_risk?.mode === 'SOURCE_CONSTRAINED' && !financialEvidenceIsCurrent(financial)) return;
    if (!run) resetAdmission();
    else {
      setAdvisoryEpoch(epoch => epoch + 1);
      setCompleted(null);
      if (assetEnabled) setAssetRunStarted(true);
    }
    const controller = new AbortController();
    pending.current = { controller, run };
    setWorking(run ? 'running' : 'checking');
    setError('');
    try {
      let submitted = run ? proposal : baseProposal;
      if (!run && assetRequest && selection) {
        const draft = await api.assetPolicyPreview(assetRequest, selection, controller.signal);
        if (controller.signal.aborted) return;
        submitted = { ...baseProposal, minimum_order_notional: assetRequest.minimum_order_notional, asset_amm_policy: draft.policy };
      }
      if (!submitted) return;
      const evidence = run && admission?.status === 'ELIGIBLE'
        ? await api.runGeneralizedPaper(submitted, admission.binding, controller.signal)
        : await api.paperEligibility(submitted, controller.signal);
      if (controller.signal.aborted) return;
      // Recheck the shared cache before publishing a response. Explorer can refresh it
      // while this workspace is hidden and React is still committing the update.
      const latestQuery = queryClient.getQueryState<typeof catalog>(generalizedDiscoveryQuery.queryKey);
      const latest = latestQuery?.data;
      const latestDecision = latest?.eligibility.find(item => marketUniverseKey(item.identity) === market);
      if (latest?.catalog_fingerprint !== catalogFingerprint || latest?.network !== catalogNetwork ||
          latestDecision?.metadata_fingerprint !== discoveryDecision?.metadata_fingerprint)
        throw new Error('Discovery changed while the request was in progress. Check eligibility again.');
      if (!('status' in evidence)) {
        // The client validated the result against the submitted proposal and binding.
        // Inputs can expire while an already-started local worker is finishing.
        setCompleted({ evidence, receivedAt: new Date().toISOString() });
        return;
      }
      if (latestQuery?.status === 'error' || latest?.availability !== availability ||
          (availability === 'AVAILABLE' && Date.now() >= marketCatalogDeadline(latest)))
        throw new Error('Discovery changed while the request was in progress. Check eligibility again.');
      if (evidence.status === 'ELIGIBLE' && (evidence.binding.catalog_fingerprint !== catalogFingerprint ||
          evidence.binding.metadata_fingerprint !== discoveryDecision?.metadata_fingerprint || !financialMatches(evidence) ||
          !paperAdmissionIsCurrent(evidence)))
        throw new Error('Discovery or financial evidence changed. Refresh discovery and check eligibility again.');
      setAdmission(evidence);
      setAssetPolicy(evidence.status === 'ELIGIBLE' ? submitted.asset_amm_policy ?? null : null);
    } catch (e) {
      if (!controller.signal.aborted) {
        setAdmission(null);
        setAssetPolicy(null);
        setError(e instanceof Error ? e.message : 'The local PAPER request failed.');
      }
    } finally {
      if (pending.current?.controller === controller) {
        pending.current = null;
        setWorking(null);
      }
    }
  }

  const result = completed?.evidence;
  const advisoryResult = result && selection && catalogMatches &&
    marketUniverseKey(result.proposal.identity) === market &&
    admission?.binding?.configuration_fingerprint === result.admission.binding.configuration_fingerprint &&
    paperAdmissionIsCurrent(result.admission) ? result : null;

  const availableScenarios = guided && !advanced
    ? scenarios.filter(item => guidedPaperScenarios.includes(item.name) || item.name === scenario)
    : scenarios;
  const scenarioDescription = scenarios.find(item => item.name === scenario)?.description;

  return <Panel title={guided ? 'Guided PAPER research' : 'Generalized PAPER research'}>
    <div className={guided ? 'stack guidedPaper' : 'researchInset stack'}>
      {guided && <div className="guidedPaperIntro">
        <p>Choose a perpetual, enter a hypothetical price, and see how your quotes, costs and inventory respond in PAPER.</p>
        <button type="button" onClick={() => {
          setMode('Pro');
          document.getElementById('workspace-mode-pro')?.focus();
        }}>Switch to Pro</button>
      </div>}
      {!guided &&
      <p>Supply a hypothetical reference price for one discovered Core or HIP-3 perpetual. This local simulation uses synthetic prices and liquidity, with zero modeled fees. Venue fees, funding, account balances and actual margin requirements are unverified. Discovery and PAPER admission grant no trading authority.</p>}
      <GuidedPaperStep guided={guided} step={1} title="Choose a market">
        <div className="researchFilters">
          <label>Discovered perpetual
            <select value={record ? market : ''} disabled={busy || records.length === 0}
              onChange={e => changeMarket(e.target.value)}>
              <option value="">Select a perpetual</option>
              {records.map(item => <option key={marketUniverseKey(item.identity)} value={marketUniverseKey(item.identity)}>
                {item.source_coin} · {item.identity.instrument_type === 'HIP3_PERP' ? 'HIP-3' : 'Core'}
                {item.listed ? '' : ' · Delisted'}
              </option>)}
            </select>
          </label>
          {guided && <a className="workspaceLink" href={pageHref('Markets')}>Browse Market Explorer</a>}
          <button type="button" disabled={busy || isFetching} onClick={() => {
            resetAdmission();
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
          catalogCurrent ? `${catalogNetwork} metadata available. Check PAPER eligibility for your scenario.` :
            'Discovery metadata expired. Refresh to check PAPER eligibility.' :
          `Discovery ${availability?.toLowerCase() ?? 'unavailable'}.`}</p>
        {guided && record && <p><strong>{record.source_coin}</strong> · {record.identity.network} · {record.identity.dex || 'Core'} · {catalogCurrent ? 'Current metadata' : 'Metadata unavailable or stale'}</p>}
        {guided && active && record && discoveryDecision && catalogFingerprint && catalogNetwork && <ObservedMarketSummary
          active={catalogCurrent && discoveryDecision.discovery_eligible}
          scope={{ network: catalogNetwork, catalogFingerprint, markets: [{
            key: market, metadataFingerprint: discoveryDecision.metadata_fingerprint,
            universeIndex: record.universe_index, listed: record.listed,
          }] }}
        />}
        <div hidden={!advanced}>
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
        </div>
      </GuidedPaperStep>
      <GuidedPaperStep guided={guided} step={2} title="Choose a scenario">
        <div className="researchFilters">
          <label>Synthetic reference price
            <input value={price} inputMode="decimal" maxLength={24} disabled={busy}
              onChange={e => { setPrice(e.target.value); resetAdmission(); }} />
          </label>
          <label>PAPER scenario
            <select value={scenario} disabled={busy} onChange={e => { setScenario(e.target.value); resetAdmission(); }}>
              {availableScenarios.map(item => <option key={item.name} value={item.name}>{item.name.replaceAll('_', ' ')}</option>)}
            </select>
          </label>
        </div>
        {guided && <p>{scenarioDescription ?? 'Scenario catalog unavailable.'} Enter your own hypothetical starting price in quote units per unit of the asset. Public observations above are for research only.</p>}
        {guided && <button type="button" aria-expanded={showAdvanced} aria-controls="paper-advanced-controls"
          onClick={() => setShowAdvanced(!showAdvanced)}>{showAdvanced ? 'Hide' : 'Show'} advanced controls</button>}
        {guided && !advanced && (assetEnabled || riskEnabled || funding) &&
          <p>Advanced settings are active from your previous configuration.</p>}
        <div id="paper-advanced-controls" hidden={!advanced}>
          <div className="researchFilters">
            <label><input type="checkbox" checked={funding} disabled={busy} onChange={e => { setFunding(e.target.checked); resetAdmission(); }} />
              Apply hypothetical funding at each one-second interval
            </label>
            <label>PAPER research mode
              <select value={assetEnabled ? 'asset' : 'standard'} onChange={e => {
                resetAdmission();
                setAssetAdvisory(null);
                setAssetDraft(initialAssetDraft);
                setAssetEnabled(e.target.value === 'asset');
              }}>
                <option value="standard">Standard PAPER</option>
                <option value="asset">Asset-aware PAPER</option>
              </select>
            </label>
          </div>
          {assetEnabled && <PaperAssetConfiguration draft={assetDraft} record={record}
            defaults={defaults.data?.policy.controls} loading={defaults.isFetching}
            error={assetError || defaults.error?.message || ''} advisory={assetAdvisory?.snapshot_fingerprint}
            onChange={next => { resetAdmission(); setAssetDraft(next); }}
            onRemoveAdvisory={() => { resetAdmission(); setAssetAdvisory(null); }} />}
          <PaperRiskConfiguration draft={riskDraft} evidence={financial} current={currentFinancial}
            error={riskError} onChange={next => { resetAdmission(); setRiskDraft(next); }} />
        </div>
      </GuidedPaperStep>
      <GuidedPaperStep guided={guided} step={3} title="Check eligibility and run PAPER">
        {guided && <p>The server checks the market and your inputs before enabling a simulation. The risk check can limit or stop modeled quoting when the scenario runs.</p>}
        <div className="researchFilters">
          <button type="button" disabled={!baseProposal || (assetEnabled && (!assetRequest || !assetSelectionCurrent || (!!assetAdvisory && !currentAssetAdvisory))) ||
            busy || isFetching || financialPending || !catalogCurrent} onClick={() => void submit(false)}>Check PAPER eligibility</button>
          <button type="button" disabled={!proposal || !ready || busy} onClick={() => void submit(true)}>Run local PAPER</button>
        </div>
        {working && <p role="status">{working === 'running' ? 'Running local PAPER simulation…' : 'Checking PAPER eligibility…'}</p>}
        {handoffError && <p role="alert">The market selection is out of date. Refresh discovery and choose a current market.</p>}
        {error && <p role="alert">{error}</p>}
        {admission && <div role="status">
          {admission.status === 'ELIGIBLE' ? <>
            <p>{expired || !paperAdmissionIsCurrent(admission) ?
              'PAPER eligibility expired. Check eligibility again.' : !catalogMatches ?
                'Discovery evidence changed. Refresh discovery and check eligibility again.' : admission.explanation}</p>
            {ready && <p>Eligibility valid until <time dateTime={admission.valid_until}>{admission.valid_until}</time></p>}
            {assetRunStarted && !expired && <p>Check eligibility again to start another asset-aware run.</p>}
          </> : <p>{assetPaperReasonText[admission.reason] ?? admission.explanation}</p>}
          {admission.status !== 'ELIGIBLE' && <p><code>{admission.reason}</code> · {admission.checks.join(', ').replaceAll('_', ' ')}</p>}
        </div>}
      </GuidedPaperStep>
      <GuidedPaperStep guided={guided} step={4} title="Review results">
        <h3 id="paper-results" tabIndex={-1} hidden={!resultsOnly}>PAPER results</h3>
        {guided && !completed && <p>Complete an eligible simulation to review hypothetical P&amp;L, fees, funding, inventory and risk.</p>}
        {completed && <PaperResult completed={completed} guided={guided && !advanced} />}
        {guided && advisoryResult && <p>Use Market Eligibility to see the evidence behind a suitability finding. Quote Economics evaluates the costs behind a retained simulated quote.</p>}
        {selection && !isFetching && !busy && <div hidden={guided && !advanced && !advisoryResult}><GeneralizedPaperAdvisory
          key={JSON.stringify([market, catalogFingerprint, financialGeneration, advisoryEpoch, advisoryResult?.advisory_receipt])}
          selection={selection} proposal={proposal} paperRun={advisoryResult} guided={guided && !advanced} catalogCurrent={catalogCurrent}
          onAttachAdvisory={assetEnabled && assetSelectionCurrent ? snapshot => {
            resetAdmission();
            setAssetAdvisory(snapshot);
          } : undefined} /></div>}
      </GuidedPaperStep>
    </div>
  </Panel>;
}

function PaperResult({ completed, guided }: { completed: CompletedPaper; guided: boolean }) {
  const { evidence: result, receivedAt } = completed;
  const { profile, binding, valid_until: validUntil } = result.admission;
  const { economics } = profile;
  const { metrics, vault } = result.result;
  const riskStates = Object.entries(metrics.risk_state_counts ?? {})
    .filter(([, count]) => count > 0)
    .map(([state, count]) => `${state.toLowerCase()} in ${count} ${count === 1 ? 'frame' : 'frames'}`);
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
    <h3>Completed PAPER research · Historical result</h3>
    <p role="status">Simulated PAPER result for {profile.exchange_coin} · {metrics.frame_count} frames · {metrics.fill_count} fills</p>
    <p>{profile.metadata.identity.network} · {profile.metadata.identity.dex || 'Core'} · {profile.metadata.identity.instrument_type === 'HIP3_PERP' ? 'HIP-3' : 'Core perpetual'}</p>
    <p>{result.proposal.asset_amm_policy ? 'Asset-aware PAPER' : 'Standard PAPER'} · {result.proposal.scenario.replaceAll('_', ' ')}</p>
    <p>Synthetic reference input {accountingValue(profile.simulated_reference_price)} · Synthetic top depth {accountingValue(profile.synthetic_top_depth_quote)} hypothetical quote units.</p>
    <p>Modeled maker fee {accountingValue(economics.maker_fee_bps)} bps · Modeled taker fee {accountingValue(economics.taker_fee_bps)} bps.
      {' '}{economics.funding_interval_seconds === null ? 'Hypothetical funding disabled.' :
        `Hypothetical funding interval ${economics.funding_interval_seconds} s.`}</p>
    <p>Equity, P&amp;L, fees, funding and reservation use hypothetical quote units. Inventory is simulated.
      {' '}{result.research_risk ? 'Public market observations and modeled risk are shown below.' :
        'Exchange collateral, margin, liquidation, leverage, settlement and account balances are unverified.'}</p>
    <dl className="researchDetails">
      {(guided ? fields.filter((_, index) => [2, 5, 6, 8].includes(index)) : fields).map(([label, amount]) => <div key={label}><dt>{label}</dt><dd>{accountingValue(amount)}</dd></div>)}
    </dl>
    {guided && <>
      <p>Simulated Risk Firewall status · {riskStates.join(', ') || 'Unavailable'}</p>
      {!result.research_risk && <p>Market-specific margin assessment unavailable for this run.</p>}
    </>}
    {guided && <p>Simulated P&amp;L describes this scenario only. Actual returns are unknown.</p>}
    {result.research_risk && result.admission.risk_model && result.admission.risk_source_status &&
      <PaperRiskEvidence risk={result.research_risk} model={result.admission.risk_model}
        sourceStatus={result.admission.risk_source_status} />}
    <PaperAssetEvidence result={result} />
    <details>
      <summary>Result fingerprint and provenance</summary>
      <p>Captured source evidence <code>· {marketUniverseKey(profile.metadata.identity)}</code></p>
      <p>Metadata observed at <time dateTime={profile.metadata.observed_at}>{profile.metadata.observed_at}</time>.</p>
      <p>Simulation started at <time dateTime={result.started_at}>{result.started_at}</time>.
        {' '}Original eligibility was valid until <time dateTime={validUntil}>{validUntil}</time>.
        {' '}Result received at <time dateTime={receivedAt}>{receivedAt}</time>.</p>
      <p>Reference confidence and timestamps describe the synthetic scenario.</p>
      <dl className="researchDetails">
        <div><dt>Catalog fingerprint</dt><dd><code>{binding.catalog_fingerprint}</code></dd></div>
        <div><dt>Metadata fingerprint</dt><dd><code>{binding.metadata_fingerprint}</code></dd></div>
        <div><dt>Configuration fingerprint</dt><dd><code>{binding.configuration_fingerprint}</code></dd></div>
        <div><dt>Result fingerprint</dt><dd><code>{result.result_fingerprint}</code></dd></div>
      </dl>
    </details>
  </section>;
}
