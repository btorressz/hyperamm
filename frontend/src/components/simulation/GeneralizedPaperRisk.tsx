import { useId } from 'react';
import type { FinancialEvidence, FinancialSourceStatus, PaperRiskResult, ResearchMarginMode, ResearchRiskModel,
  ResearchRiskSettings, StressAssumption, StressField } from '../../types/marketRisk';
import { maxResearchStresses, stressFields } from '../../types/marketRisk';
import { accountingValue } from '../../utils/researchEvidence';

export interface RiskDraft {
  mode: 'OFF' | ResearchRiskSettings['mode'];
  marginMode: ResearchMarginMode;
  capital: string;
  initial: string;
  maintenance: string;
  leverage: string;
  ceiling: string;
  rate: string;
  stresses: StressAssumption[];
}

export const initialRiskDraft: RiskDraft = {
  mode: 'OFF', marginMode: 'ISOLATED', capital: '', initial: '', maintenance: '',
  leverage: '', ceiling: '', rate: '', stresses: [],
};

const marginModeLabels = {
  ISOLATED: 'Isolated research',
  STRICT_ISOLATED: 'Strict isolated',
  NO_CROSS: 'Isolated with margin removal (no cross)',
  CROSS_ELIGIBLE: 'Cross eligible at the venue',
  ISOLATED_UNSPECIFIED: 'Isolated restrictions unspecified',
  UNKNOWN: 'Unavailable',
};
const sourceLabels: Record<FinancialSourceStatus, string> = {
  SOURCE_OBSERVED: 'Exchange observed', STALE: 'Stale', UNAVAILABLE: 'Unavailable', UNSUPPORTED: 'Unsupported',
};
const issueLabels = {
  COLLATERAL_MISSING: 'The public market record omits a collateral token.',
  COLLATERAL_INVALID: 'The public market record has an unsupported collateral token index.',
  TOKEN_METADATA_UNAVAILABLE: 'The public spot token registry is unavailable.',
  TOKEN_UNRESOLVED: 'The collateral index does not resolve to a supported spot token.',
  MARGIN_MODE_MISSING: 'The public market record omits the margin mode.',
  MARGIN_MODE_UNSUPPORTED: 'The public market record reports an unsupported margin mode.',
  MARGIN_MODE_DEPRECATED_ONLY: 'The legacy isolated flag does not describe current margin restrictions.',
  MARGIN_TABLE_MISSING: 'The public market record omits a usable margin table.',
  MARGIN_TABLE_INVALID: 'The reported leverage and margin table do not form a supported tier schedule.',
  MARKET_DELISTED: 'The perpetual is delisted.',
};
const stressLabels: Record<StressField, string> = {
  price_shock_bps: 'Price shock', collateral_loss_bps: 'Collateral haircut', capital_reduction_bps: 'Capital reduction',
  funding_cost_bps: 'Funding cost surcharge', fees_bps: 'Fee surcharge',
};

function Fields({ entries }: { entries: [string, React.ReactNode][] }) {
  return <dl className="researchDetails">
    {entries.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
  </dl>;
}

export function PaperFinancialEvidence({ evidence, current, loading, error }: {
  evidence?: FinancialEvidence; current: boolean; loading: boolean; error?: string;
}) {
  const observation = evidence?.observation;
  const collateral = observation?.collateral;
  const margin = observation?.margin;
  const issue = evidence?.source_constraint_reason;
  return <section aria-label="Public collateral and margin evidence">
    <h3>Public collateral and margin evidence</h3>
    <p role="status">{loading ? 'Loading public financial evidence…' : error ||
      (!evidence ? 'Financial metadata is unavailable for this selection.' : !current
        ? 'Financial evidence is stale. Refresh discovery to use current observations.'
        : `Financial metadata status is ${sourceLabels[evidence.status].toLowerCase()}.`)}</p>
    {observation && <Fields entries={[
      ['Collateral asset', collateral ? `${collateral.symbol} · token index ${collateral.index}` :
        observation.collateral_status === 'UNSUPPORTED' ? 'Unsupported' : 'Unavailable'],
      ['Collateral token identity', collateral ? <code>{collateral.network} / {collateral.namespace} / {collateral.token_id}</code> : 'Unavailable'],
      ['Collateral source', collateral ? <>{observation.collateral_source} · <time dateTime={collateral.observed_at}>{collateral.observed_at}</time></> : sourceLabels[observation.collateral_status]],
      ['Observed margin mode', marginModeLabels[observation.margin.mode]],
      ['Margin source', <>{observation.source} · <time dateTime={observation.metadata.observed_at}>{observation.metadata.observed_at}</time></>],
      ['Margin evidence', sourceLabels[observation.margin_status]],
      ['Financial evidence valid until', <time dateTime={evidence.valid_until}>{evidence.valid_until}</time>],
    ]} />}
    {margin && margin.tiers.length > 0 && <div>
      <h4>Observed margin tiers</h4>
      <p>Table {margin.table_id} · {margin.tier_source === 'EXPLICIT_TABLE' ? 'Exchange-reported tiers' : 'Documented table ID rule'}
        {margin.tiers.length > 1 && issue !== 'RISK_SOURCE_UNSUPPORTED' &&
          observation?.metadata.identity.instrument_type === 'CORE_PERP' && collateral?.symbol === 'USDC'
          ? ' · published thresholds in USDC' : ''}</p>
      <ul>{margin.tiers.map(tier => <li key={tier.lower_bound}>
        Lower bound {accountingValue(tier.lower_bound)} · maximum leverage {tier.max_leverage}×
      </li>)}</ul>
    </div>}
    {!!observation?.issues.length && <ul>{observation.issues.map(code =>
      <li key={code}>{issueLabels[code as keyof typeof issueLabels]}</li>)}</ul>}
    {current && issue && <p>Source-constrained research is unavailable. {issue === 'RISK_SOURCE_UNSUPPORTED'
      ? 'The observed collateral or tier denomination is outside the supported model.'
      : issue === 'RISK_MARGIN_MODE_UNSUPPORTED' ? 'An explicit supported exchange margin mode is required.'
      : 'Current public collateral and margin observations are required.'}</p>}
    <p>Public market metadata describes the instrument and venue policy. Account mode, balances and settlement remain unavailable.</p>
  </section>;
}

export function PaperRiskConfiguration({ draft, evidence, current, error, onChange }: {
  draft: RiskDraft; evidence?: FinancialEvidence; current: boolean; error?: string; onChange: (next: RiskDraft) => void;
}) {
  const errorId = useId();
  const sourceModes = current ? evidence?.source_margin_modes ?? [] : [];
  const source = draft.mode === 'SOURCE_CONSTRAINED';
  const observedMode = current ? evidence?.observation?.margin.mode : undefined;
  const modes: ResearchMarginMode[] = source ? sourceModes :
    observedMode === 'STRICT_ISOLATED' || observedMode === 'NO_CROSS' ? ['ISOLATED', observedMode] : ['ISOLATED'];
  const update = (values: Partial<RiskDraft>) => onChange({ ...draft, ...values });
  const field = (label: string, key: 'capital' | 'initial' | 'maintenance' | 'leverage' | 'ceiling' | 'rate') =>
    <label>{label}<input inputMode="decimal" maxLength={32} value={draft[key]} onChange={e => update({ [key]: e.target.value })} /></label>;
  function addStress() {
    let index = 1;
    while (draft.stresses.some(item => item.name === `stress_${index}`)) index++;
    update({ stresses: [...draft.stresses, { name: `stress_${index}`, price_shock_bps: '0', collateral_loss_bps: '0',
      capital_reduction_bps: '0', funding_cost_bps: '0', fees_bps: '0' }] });
  }

  return <fieldset className="paperRiskFieldset" aria-describedby={error ? errorId : undefined}>
    <legend>Research risk</legend>
    <div className="researchFilters">
      <label>Risk mode
        <select value={draft.mode} onChange={e => update({ mode: e.target.value as RiskDraft['mode'], marginMode: 'ISOLATED',
          leverage: '', ceiling: '', rate: '' })}>
          <option value="OFF">Existing PAPER</option>
          <option value="HYPOTHETICAL">Hypothetical risk research</option>
          <option value="SOURCE_CONSTRAINED" disabled={!sourceModes.length}>Source-constrained risk research</option>
        </select>
      </label>
    </div>
    {source && <p>Exchange-observed market constraints + hypothetical PAPER valuation and capital.</p>}
    {draft.mode === 'HYPOTHETICAL' && <p>Hypothetical margin fractions, capital and stress assumptions apply to one PAPER market.</p>}
    {draft.mode !== 'OFF' && <>
      <div className="researchFilters">
        {field('Research capital (PAPER quote units)', 'capital')}
        <label>Research margin mode
          <select value={modes.includes(draft.marginMode) ? draft.marginMode : ''} disabled={modes.length === 0}
            onChange={e => update({ marginMode: e.target.value as ResearchMarginMode })}>
            {!modes.includes(draft.marginMode) && <option value="">Select a supported mode</option>}
            {modes.map(mode => <option key={mode} value={mode}>{marginModeLabels[mode]}</option>)}
          </select>
        </label>
        {source ? <>
          {field('Research leverage (whole number)', 'leverage')}
          {field(`Hypothetical valuation (${evidence?.observation?.collateral?.symbol ?? 'collateral'} per PAPER quote unit)`, 'rate')}
        </> : <>
          {field('Initial margin fraction', 'initial')}
          {field('Maintenance margin fraction', 'maintenance')}
          {field('Research leverage (optional)', 'leverage')}
          {!!draft.leverage.trim() && field('Declared leverage ceiling', 'ceiling')}
        </>}
      </div>
      {source && <p>{sourceModes.length
        ? `The lowest-notional tier allows up to ${evidence?.observation?.margin.tiers[0]?.max_leverage}× research leverage. The server checks the applicable tier for each exposure.`
        : 'Current collateral and margin evidence is required. Refresh discovery or choose another risk mode.'}
        {' '}The conversion rate is a fixed scenario assumption. Live FX is unavailable.</p>}
      <fieldset className="paperRiskFieldset">
        <legend>Stress assumptions</legend>
        <p>Use basis points. A negative price shock models a decline.</p>
        {draft.stresses.map((stress, index) => {
          const change = (key: keyof StressAssumption, value: string) => update({
            stresses: draft.stresses.map((entry, position) => position === index ? { ...entry, [key]: value } : entry),
          });
          return <fieldset className="paperRiskFieldset" key={index}>
            <legend>Stress {index + 1}</legend>
            <div className="researchFilters">
              <label>Stress name<input value={stress.name} maxLength={32} onChange={e => change('name', e.target.value)} /></label>
              {stressFields.map(key => <label key={key}>{stressLabels[key]} (bps)
                <input inputMode="decimal" value={stress[key]} maxLength={32} onChange={e => change(key, e.target.value)} />
              </label>)}
              <button type="button" onClick={() => update({ stresses: draft.stresses.filter((_, position) => position !== index) })}>
                Remove stress {index + 1}
              </button>
            </div>
          </fieldset>;
        })}
        <button type="button" disabled={draft.stresses.length >= maxResearchStresses} onClick={addStress}>Add stress scenario</button>
      </fieldset>
    </>}
    {error && <p id={errorId} role="status">{error}</p>}
  </fieldset>;
}

export function PaperRiskEvidence({ risk, model, sourceStatus }: {
  risk: PaperRiskResult; model: ResearchRiskModel; sourceStatus: FinancialSourceStatus;
}) {
  const { final_snapshot: snapshot, frames } = risk;
  const unit = model.margin_unit.kind === 'HYPOTHETICAL_QUOTE' ? 'PAPER quote units' : model.margin_unit.symbol;
  const amount = (value: string, denomination = unit) => `${accountingValue(value)} ${denomination}`;
  const quote = (value: string) => amount(value, 'PAPER quote units');
  const base = (value: string) => amount(value, 'base units');
  const ratio = (value: string | null) => value === null ? 'Unavailable' : accountingValue(value, true);
  const source = model.source;
  const valuation = model.settings.valuation;
  const retired = frames.filter(frame => frame.margin_retired_quotes).length;
  const states = [...new Set(frames.map(frame => frame.state))];
  const exposure = snapshot?.exposure;
  const margin = snapshot?.margin;

  return <section aria-label="Modeled research risk" className="paperRiskResults">
    <h3>Modeled research risk</h3>
    <p>{valuation ? 'Exchange-observed market constraints + hypothetical PAPER valuation and capital.' :
      'Hypothetical risk research with a separate modeled capital budget.'}</p>
    <p>PAPER only. Prices, liquidity and fills are synthetic. Modeled requirements and headroom use hypothetical capital.
      Account balances, shared-capital netting and verified liquidation estimates are unavailable.</p>
    <Fields entries={[
      ['Research model', <code>{model.version} · {model.formula}</code>],
      ['Research margin mode', marginModeLabels[model.settings.margin_mode]],
      ['Modeled financial unit', unit],
      ['Declared research capital', quote(model.settings.capital_paper_quote)],
      ['Research leverage', model.settings.leverage ? `${accountingValue(model.settings.leverage)}×` : 'Unspecified'],
      ['Financial source status at admission', sourceLabels[sourceStatus]],
      ['Observed collateral', source?.collateral ? <>{source.collateral.symbol} · <code>{source.collateral.network} / {source.collateral.namespace} / {source.collateral.token_id}</code></> : 'Unavailable'],
      ['Captured margin policy source', source ? <>{source.source} · <time dateTime={source.metadata.observed_at}>{source.metadata.observed_at}</time></> : 'Unavailable'],
      ['Fixed hypothetical valuation', valuation ? `${amount(valuation.collateral_per_paper_quote)} per PAPER quote unit` : 'PAPER quote only'],
    ]} />
    <details><summary>Risk model and source fingerprints</summary>
      <Fields entries={[
        ['Research model fingerprint', <code>{risk.model_fingerprint}</code>],
        ['Financial source fingerprint', model.source_fingerprint ? <code>{model.source_fingerprint}</code> : 'Unavailable'],
        ['Captured collateral observation', source?.collateral ? <time dateTime={source.collateral.observed_at}>{source.collateral.observed_at}</time> : 'Unavailable'],
        ['Initial margin fraction', model.settings.initial_margin_fraction ?? 'Source tier formula'],
        ['Maintenance margin fraction', model.settings.maintenance_margin_fraction ?? 'Source tier formula'],
        ['Declared leverage ceiling', model.settings.max_leverage ? `${model.settings.max_leverage}×` : 'Unspecified'],
      ]} />
    </details>
    {snapshot && exposure && margin ? <>
      <h4>Exposure at the final frame</h4>
      <p>Synthetic valuation time <time dateTime={snapshot.valuation_time}>{snapshot.valuation_time}</time></p>
      <Fields entries={[
        ['Signed position', base(exposure.signed_base)], ['Absolute position notional', quote(exposure.absolute_notional)],
        ['Gross long exposure', quote(exposure.gross_long_notional)], ['Gross short exposure', quote(exposure.gross_short_notional)],
        ['Proposed bid exposure', quote(exposure.proposed_bid_notional)], ['Proposed ask exposure', quote(exposure.proposed_ask_notional)],
        ['Resting bid exposure', quote(exposure.resting_bid_notional)], ['Resting ask exposure', quote(exposure.resting_ask_notional)],
        ['Effective bid exposure', quote(exposure.effective_bid_notional)], ['Effective ask exposure', quote(exposure.effective_ask_notional)],
        ['Projected long position', base(exposure.projected_long_base)], ['Projected short position', base(exposure.projected_short_base)],
        ['Capital concentration', ratio(exposure.capital_concentration)], ['Inventory utilization', ratio(exposure.inventory_utilization)],
      ]} />
      <h4>Modeled margin and headroom</h4>
      <Fields entries={[
        ['Modeled budget after PAPER P&L', amount(margin.capital)],
        ['Initial requirement', amount(margin.current.initial)], ['Maintenance requirement', amount(margin.current.maintenance)],
        ['Projected initial requirement', amount(margin.projected_initial)], ['Projected maintenance requirement', amount(margin.projected_maintenance)],
        ['Initial headroom', amount(margin.initial_headroom)], ['Maintenance headroom', amount(margin.maintenance_headroom)],
        ['Projected headroom', amount(margin.projected_headroom)], ['Projected margin utilization', ratio(margin.projected_utilization)],
        ...(['Current', 'Projected long', 'Projected short'] as const).map((label, index): [string, string] => {
          const requirement = [margin.current, margin.projected_long, margin.projected_short][index];
          return [`${label} tier and leverage`, requirement.tier_lower_bound !== null
            ? `From ${amount(requirement.tier_lower_bound)} · cap ${requirement.source_max_leverage}× · modeled at ${requirement.margin_leverage}× · ${requirement.leverage_supported ? 'supported' : 'requested leverage unsupported'}`
            : model.settings.leverage ? `${model.settings.leverage}× · ${requirement.leverage_supported ? 'supported' : 'unsupported'}` : 'No leverage assumption'];
        }),
      ]} />
      {!!snapshot.stresses.length && <section aria-label="Modeled stress results">
        <h4>Modeled stress results</h4>
        {snapshot.stresses.map(stress => <div className="paperRiskStress" key={stress.assumptions.name}>
          <h5>{stress.assumptions.name} · {stress.feasible ? 'Feasible' : 'Infeasible'}</h5>
          <Fields entries={[
            ...stressFields.map((key): [string, string] => [stressLabels[key], amount(stress.assumptions[key], 'basis points')]),
            ['Adverse modeled P&L', quote(stress.adverse_pnl_paper_quote)],
            ['Modeled funding and fee costs', quote(stress.costs_paper_quote)],
            ['Stressed projected headroom', amount(stress.margin.projected_headroom)],
            ['Headroom deterioration', amount(stress.headroom_deterioration)],
            ['Tier transition', stress.tier_changed ? 'Tier changed' : 'No tier change'],
          ]} />
        </div>)}
      </section>}
    </> : <p role="status">Final modeled exposure is unavailable. The Risk Firewall recorded invalid exposure.</p>}
    <h4>Risk Firewall</h4>
    <p>Recorded states {states.join(', ')}. Margin-related quote retirement occurred in {retired} of {frames.length} frames.</p>
    <p>The Firewall can widen, reduce or retire the existing PAPER ladder when modeled headroom or leverage is insufficient.</p>
    <details><summary>Per-frame Risk Firewall decisions</summary>
      <ol className="paperRiskFrames">
        {frames.map(frame => <li key={frame.sequence}>
          <strong>Frame {frame.sequence} · {frame.state}</strong>
          <Fields entries={[
            ['Candidate quotes', frame.candidate_quotes], ['Authorized quotes', frame.authorized_quotes],
            ['Projected headroom', frame.projected_headroom === null ? 'Unavailable' : amount(frame.projected_headroom)],
            ['Margin quote retirement', frame.margin_retired_quotes ? 'Retired' : 'No retirement'],
          ]} />
          {!!frame.decision_reasons.length && <ul>{frame.decision_reasons.map((reason, index) =>
            <li key={index}>{reason}</li>)}</ul>}
        </li>)}
      </ol>
    </details>
  </section>;
}
