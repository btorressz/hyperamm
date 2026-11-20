import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { advisoryIssueText, advisoryOperations } from '../../types/advisory';
import type {
  AdvisoryOperation, AdvisoryPaperBinding, AdvisoryRecommendation, AdvisoryRequest, AdvisoryResponse,
  AdvisorySelection, FundingMode, QuoteAdvisory,
} from '../../types/advisory';
import type { GeneralizedPaperResult, PaperProposal } from '../../types/generalizedPaper';
import { boundedRiskInput } from '../../utils/marketRisk';
import { accountingValue } from '../../utils/researchEvidence';

type Selectors = Omit<AdvisoryRequest, 'identity' | 'catalog_fingerprint'>;
const operationNames: Record<AdvisoryOperation, string> = {
  DISCOVERY: 'Discovery', STANDARD_PAPER: 'Standard PAPER', HYPOTHETICAL_RISK: 'Hypothetical risk',
  SOURCE_CONSTRAINED_RISK: 'Source-constrained risk', FUNDING_BASIS: 'Funding/Basis', QUOTE_ECONOMICS: 'Quote Economics',
};
const label = (value: string) => value.toLowerCase().replaceAll('_', ' ');
const price = (amount: string | null | undefined, unit: string) =>
  amount == null ? 'Unavailable' : `${accountingValue(amount)} ${unit}`;

function useAdvisory(selection: AdvisorySelection, slot: string, paper?: AdvisoryPaperBinding) {
  const [request, setRequest] = useState<{ selectors: Selectors; attempt: number } | null>(null);
  const [expiredFingerprint, setExpiredFingerprint] = useState('');
  const query = useQuery({
    queryKey: ['market-advisory', slot, selection.metadata.identity, selection.catalog_fingerprint, request],
    queryFn: ({ signal }) => {
      if (!request) throw new Error('Select an advisory operation.');
      return api.advisory({
        identity: selection.metadata.identity, catalog_fingerprint: selection.catalog_fingerprint, ...request.selectors,
      }, selection, paper, signal);
    },
    enabled: request !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    gcTime: 0,
  });
  const snapshot = request ? query.data : undefined;
  useEffect(() => {
    if (!snapshot) return;
    const timer = window.setTimeout(() => setExpiredFingerprint(snapshot.snapshot_fingerprint),
      Math.max(0, Date.parse(snapshot.valid_until) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [snapshot]);
  const expired = snapshot !== undefined &&
    (snapshot.snapshot_fingerprint === expiredFingerprint || Date.now() >= Date.parse(snapshot.valid_until));
  return {
    run: (selectors: Selectors) => setRequest(previous => ({ selectors, attempt: (previous?.attempt ?? 0) + 1 })),
    clear: () => setRequest(null),
    data: expired ? undefined : snapshot,
    loading: request !== null && query.isFetching,
    error: request !== null ? query.error?.message : undefined,
    expired,
  };
}

function QueryStatus({ query, pending }: { query: ReturnType<typeof useAdvisory>; pending: string }) {
  if (query.loading) return <p role="status">{pending}</p>;
  if (query.error) return <p role="alert">{query.error}</p>;
  if (query.expired) return <p role="status">Advisory evidence expired. Evaluate again for current evidence.</p>;
  return null;
}

function Issues({ snapshot }: { snapshot: AdvisoryResponse }) {
  return snapshot.issues.length > 0 && <ul>
    {snapshot.issues.map(issue => <li key={issue}>{advisoryIssueText[issue]}</li>)}
  </ul>;
}

function Evidence({ result, snapshot }: { result: AdvisoryRecommendation; snapshot: AdvisoryResponse }) {
  const sources = snapshot.snapshot.context.sources.filter(source => result.source_fingerprints.includes(source.source_fingerprint));
  return <>
    <p role="status">Status {label(result.status)} · Confidence {accountingValue(result.confidence, true)} · {label(result.provenance)}</p>
    <ul>{result.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
    {result.missing_requirements && result.missing_requirements.length > 0 &&
      <p>Missing requirements · {result.missing_requirements.map(label).join(', ')}</p>}
    <details>
      <summary>Source provenance and freshness</summary>
      <p>Evaluated <time dateTime={snapshot.evaluated_at}>{snapshot.evaluated_at}</time> ·
        {' '}Valid until <time dateTime={snapshot.valid_until}>{snapshot.valid_until}</time></p>
      <p>Snapshot fingerprint <code>{snapshot.snapshot_fingerprint}</code></p>
      {sources.length === 0 ? <p>No sources support a finding.</p> :
        <ul className="researchEventList">
          {sources.map(source => <li key={source.source_fingerprint}>
            <strong>{label(source.category)}</strong> · {label(source.provenance)} · {source.source_id}
            <div>Acquired <time dateTime={source.captured_at}>{source.captured_at}</time></div>
            {source.observed_at && <div>Provider event <time dateTime={source.observed_at}>{source.observed_at}</time></div>}
            {source.observation_clock === 'LOCAL_RECEIPT' && <div>Provider event time unavailable.</div>}
            {source.scenario_at && <div>Scenario time <time dateTime={source.scenario_at}>{source.scenario_at}</time></div>}
            {source.valid_until && <div>Source valid until <time dateTime={source.valid_until}>{source.valid_until}</time></div>}
            {source.unit && <div>Unit {label(source.unit)}</div>}
            {source.limitations?.map(limit => <div key={limit}>{limit}</div>)}
            <code>{source.source_fingerprint}</code>
          </li>)}
        </ul>}
    </details>
  </>;
}

function Metrics({ title, rows }: { title: string; rows: readonly [string, ReactNode][] }) {
  return <table className="paperAdvisoryMetrics">
    <caption>{title}</caption>
    <tbody>{rows.map(([metric, value]) => <tr key={metric}>
      <th scope="row">{metric}</th><td>{value}</td>
    </tr>)}</tbody>
  </table>;
}

function EligibilityPanel({ selection, proposal, paperRun, quote, onAttachAdvisory }: {
  selection: AdvisorySelection; proposal: PaperProposal | null; paperRun: GeneralizedPaperResult | null;
  quote?: AdvisoryRequest['quote'];
  onAttachAdvisory?: (snapshot: AdvisoryResponse) => void;
}) {
  const [operation, setOperation] = useState<AdvisoryOperation>('DISCOVERY');
  const query = useAdvisory(selection, 'eligibility', paperRun ? {
    result_fingerprint: paperRun.result_fingerprint, binding: paperRun.admission.binding,
  } : undefined);
  const finding = query.data?.snapshot.market_eligibility;
  const metadata = selection.metadata;
  const checksPaper = ['STANDARD_PAPER', 'HYPOTHETICAL_RISK', 'SOURCE_CONSTRAINED_RISK'].includes(operation);
  return <section aria-labelledby="paper-advisory-eligibility">
    <h3 id="paper-advisory-eligibility">Market Eligibility</h3>
    <p>{metadata.source_coin} · {metadata.identity.instrument_type === 'HIP3_PERP' ? 'HIP-3' : 'Core'} · {metadata.identity.network}</p>
    <p>Use the PAPER eligibility check above to admit a simulation.</p>
    <div className="researchFilters">
      <label>Advisory research operation
        <select value={operation} onChange={event => {
          query.clear();
          setOperation(event.target.value as AdvisoryOperation);
        }}>
          {advisoryOperations.map(item => <option key={item} value={item}>{operationNames[item]}</option>)}
        </select>
      </label>
      <button type="button" disabled={query.loading} onClick={() => query.run({
        operation, ...(checksPaper && proposal ? { proposal } : {}),
        ...(operation === 'QUOTE_ECONOMICS' && paperRun?.advisory_receipt
          ? { paper_receipt: paperRun.advisory_receipt, quote } : {}),
      })}>Evaluate market eligibility</button>
    </div>
    <QueryStatus query={query} pending="Evaluating market eligibility…" />
    {query.data && finding && <>
      <p>{operationNames[finding.operation]} suitability · <strong>{label(finding.suitability)}</strong></p>
      <Evidence result={finding} snapshot={query.data} />
      <Issues snapshot={query.data} />
      {onAttachAdvisory && finding.operation === 'DISCOVERY' && finding.status === 'READY' && <button
        type="button" onClick={() => {
          if (query.data && Date.now() < Date.parse(query.data.valid_until)) onAttachAdvisory(query.data);
        }}>Attach discovery advisory to asset research</button>}
    </>}
  </section>;
}

function FundingEvidence({ mode, selection, paperRun }: {
  mode: FundingMode; selection: AdvisorySelection; paperRun: GeneralizedPaperResult | null;
}) {
  const observed = mode === 'OBSERVED';
  const query = useAdvisory(selection, mode, paperRun ? {
    result_fingerprint: paperRun.result_fingerprint, binding: paperRun.admission.binding,
  } : undefined);
  const finding = query.data?.snapshot.funding_basis;
  const title = observed ? 'Observed public funding and basis' : 'Synthetic PAPER funding and basis';
  const heading = observed ? 'paper-advisory-observed' : 'paper-advisory-synthetic';
  const receipt = paperRun?.advisory_receipt;
  const priceUnit = observed ? 'venue quote per base' : 'hypothetical quote per base';
  return <section aria-labelledby={heading}>
    <h4 id={heading}>{title}</h4>
    <p>{observed ? 'Current hourly funding can change before settlement.' :
      'Prices and funding come from the final synthetic simulation frame.'}</p>
    <button type="button" disabled={query.loading || (!observed && !receipt)} onClick={() => query.run({
      operation: 'FUNDING_BASIS', funding_mode: mode, ...(observed ? {} : { paper_receipt: receipt }),
    })}>{observed ? 'Inspect observed funding' : 'Inspect synthetic funding'}</button>
    {!observed && !receipt && <p>Complete a local PAPER run to inspect synthetic funding.</p>}
    <QueryStatus query={query} pending={observed ? 'Loading public funding observations…' : 'Evaluating synthetic funding…'} />
    {query.data && finding && <>
      <Evidence result={finding} snapshot={query.data} />
      <Issues snapshot={query.data} />
      <Metrics title={title} rows={[
        ['Funding rate per interval', finding.funding_rate === null ? 'Unavailable' : accountingValue(finding.funding_rate, true)],
        ['Funding interval', finding.funding_interval_seconds === null ? 'Unavailable' : `${finding.funding_interval_seconds} s`],
        ['Funding direction', finding.funding_direction ? label(finding.funding_direction) : 'Unavailable'],
        ['Mark price', price(finding.mark_price, priceUnit)],
        ['Oracle price', price(finding.oracle_price, priceUnit)],
        [observed ? 'Order-book midpoint' : 'Scenario midpoint', price(finding.midpoint_price, priceUnit)],
        ['Mark–oracle basis', price(finding.mark_oracle_basis_bps, 'bps')],
        ['Mark–mid basis', price(finding.mark_mid_basis_bps, 'bps')],
        ['Basis and funding state', label(finding.state)],
        ...(observed ? [
          ['Historical posted funding observations', finding.history_count ?? 'Unavailable'],
          ['Mean posted hourly rate', finding.recent_history_mean_rate === undefined ? 'Unavailable' :
            accountingValue(finding.recent_history_mean_rate, true)],
        ] as [string, ReactNode][] : []),
      ]} />
    </>}
  </section>;
}

function QuoteMetrics({ finding }: { finding: QuoteAdvisory }) {
  const amounts = 'hypothetical quote units';
  return <Metrics title="Hypothetical quote economics" rows={[
    ['Submitted best bid', price(finding.submitted_bid, 'hypothetical quote per base')],
    ['Submitted best ask', price(finding.submitted_ask, 'hypothetical quote per base')],
    ['Gross quoted spread', price(finding.gross_spread_bps, 'bps')],
    ['Executed capture', price(finding.captured_spread_bps, 'bps')],
    ['Entry fees', price(finding.entry_fees_quote, amounts)],
    ['Hypothetical exit fees', price(finding.exit_fees_quote, amounts)],
    ['Combined fee cost', price(finding.fee_cost_bps, 'bps')],
    ['Funding carry cost (negative is a receipt)', price(finding.funding_cost_bps, 'bps')],
    ['Inventory cost', price(finding.inventory_cost_bps, 'bps')],
    ['Adverse-selection cost', price(finding.adverse_selection_cost_bps, 'bps')],
    ['Slippage cost', price(finding.slippage_cost_bps, 'bps')],
    ['Break-even capture', price(finding.break_even_capture_bps, 'bps')],
    ['Hypothetical modeled residual edge', price(finding.modeled_edge_bps, 'bps')],
    ['Attributed fill count', finding.attributed_fill_count],
    ['Matured markout count', finding.matured_markout_count],
    ['Fill coverage', label(finding.fill_coverage ?? 'unavailable')],
    ['Residual inventory', price(finding.residual_base, 'base units')],
    ['Modeled margin headroom', price(finding.projected_margin_headroom, finding.margin_headroom_unit?.symbol ?? '')],
  ]} />;
}

function QuotePanel({ selection, paperRun, onQuote }: {
  selection: AdvisorySelection; paperRun: GeneralizedPaperResult | null;
  onQuote: (quote: AdvisoryRequest['quote']) => void;
}) {
  const paper = paperRun ? { result_fingerprint: paperRun.result_fingerprint, binding: paperRun.admission.binding } : undefined;
  const cohorts = useAdvisory(selection, 'cohorts', paper);
  const query = useAdvisory(selection, 'economics', paper);
  const [sequence, setSequence] = useState('');
  const [holding, setHolding] = useState('');
  const [liquidity, setLiquidity] = useState<'MAKER' | 'TAKER'>('TAKER');
  const [slippage, setSlippage] = useState('');
  const [inventory, setInventory] = useState('');
  const [error, setError] = useState('');
  const receipt = paperRun?.advisory_receipt;
  const finding = query.data?.snapshot.quote_economics;
  const frames = cohorts.data?.quote_cohorts ?? [];

  function evaluate() {
    setError('');
    if (!receipt || sequence === '' || !frames.includes(Number(sequence))) return;
    const seconds = Number(holding);
    if (!/^\d{1,6}$/.test(holding) || !Number.isInteger(seconds) || seconds < 1 || seconds > 604800) {
      setError('Enter a holding period from 1 to 604,800 seconds.');
      return;
    }
    try {
      const quote = { sequence: Number(sequence), assumptions: {
        holding_seconds: seconds, closing_liquidity: liquidity,
        exit_slippage_bps: boundedRiskInput(slippage, '0', '10000'),
        inventory_rate_bps: boundedRiskInput(inventory, '0', '10000'),
      } };
      onQuote(quote);
      query.run({ operation: 'QUOTE_ECONOMICS', paper_receipt: receipt, quote });
    } catch {
      setError('Enter explicit slippage and inventory cost assumptions from 0 to 10,000 bps.');
    }
  }

  function clearQuote() {
    query.clear();
    onQuote(undefined);
    setError('');
  }

  return <section aria-labelledby="paper-advisory-quote">
    <h3 id="paper-advisory-quote">Quote Economics</h3>
    <p>Review attributed fills and matured markouts from a simulated quote cohort. Modeled edge is hypothetical.</p>
    {!receipt ? <p>Complete a local PAPER run to select a quote cohort.</p> :
      <button type="button" disabled={cohorts.loading} onClick={() => {
        clearQuote();
        setSequence('');
        cohorts.run({ operation: 'QUOTE_ECONOMICS', paper_receipt: receipt });
      }}>Load PAPER quote cohorts</button>}
    <QueryStatus query={cohorts} pending="Loading retained PAPER quote cohorts…" />
    {cohorts.data && frames.length === 0 && <>
      <Issues snapshot={cohorts.data} />
      <p>No quote frames are available from this receipt.</p>
    </>}
    {frames.length > 0 && <fieldset className="paperRiskFieldset">
      <legend>Quote cohort and research costs</legend>
      <div className="researchFilters">
        <label>Simulated quote cohort
          <select value={sequence} onChange={event => { clearQuote(); setSequence(event.target.value); }}>
            <option value="">Select a quote frame</option>
            {frames.map(frame => <option key={frame} value={frame}>PAPER frame {frame}</option>)}
          </select>
        </label>
        <label>Holding period in seconds
          <input inputMode="numeric" maxLength={6} value={holding} onChange={event => {
            clearQuote(); setHolding(event.target.value);
          }} />
        </label>
        <label>Residual exit liquidity
          <select value={liquidity} onChange={event => {
            clearQuote(); setLiquidity(event.target.value === 'MAKER' ? 'MAKER' : 'TAKER');
          }}>
            <option value="TAKER">Taker</option><option value="MAKER">Maker</option>
          </select>
        </label>
        <label>Exit slippage in bps
          <input inputMode="decimal" maxLength={18} value={slippage} onChange={event => {
            clearQuote(); setSlippage(event.target.value);
          }} />
        </label>
        <label>Inventory cost in bps
          <input inputMode="decimal" maxLength={18} value={inventory} onChange={event => {
            clearQuote(); setInventory(event.target.value);
          }} />
        </label>
        <button type="button" disabled={sequence === '' || query.loading} onClick={evaluate}>Evaluate quote economics</button>
      </div>
      {error && <p role="alert">{error}</p>}
    </fieldset>}
    <QueryStatus query={query} pending="Evaluating quote economics…" />
    {query.data && finding && <>
      {query.data.quote_sequence !== null && <p>PAPER frame {query.data.quote_sequence} · Risk Firewall {query.data.quote_risk_state}</p>}
      <p>{label(finding.state)} · Hypothetical PAPER model</p>
      <Evidence result={finding} snapshot={query.data} />
      <Issues snapshot={query.data} />
      {finding.status === 'READY' && <QuoteMetrics finding={finding} />}
    </>}
  </section>;
}

export function GeneralizedPaperAdvisory({ selection, proposal, paperRun, onAttachAdvisory }: {
  selection: AdvisorySelection; proposal: PaperProposal | null; paperRun: GeneralizedPaperResult | null;
  onAttachAdvisory?: (snapshot: AdvisoryResponse) => void;
}) {
  const [quote, setQuote] = useState<AdvisoryRequest['quote']>();
  return <section className="paperAdvisory" aria-labelledby="paper-advisory">
    <h2 id="paper-advisory">Research advisories</h2>
    <EligibilityPanel key={JSON.stringify(quote ?? null)} selection={selection} proposal={proposal}
      paperRun={paperRun} quote={quote} onAttachAdvisory={onAttachAdvisory} />
    <section aria-labelledby="paper-advisory-funding">
      <h3 id="paper-advisory-funding">Funding/Basis</h3>
      <FundingEvidence mode="OBSERVED" selection={selection} paperRun={null} />
      <FundingEvidence mode="PAPER" selection={selection} paperRun={paperRun} />
    </section>
    <QuotePanel selection={selection} paperRun={paperRun} onQuote={setQuote} />
  </section>;
}
