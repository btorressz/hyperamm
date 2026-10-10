import type { ReactNode } from 'react';
import type { AgentRecommendation, TerminalState } from '../../types';
import { Badge } from '../Badge';
import { Panel, Metrics } from '../TerminalPrimitives';
import { number as f, percentage, bps } from '../../utils/format';
import { evidenceTime, accountingValue } from '../../utils/researchEvidence';

const missing = 'Unavailable from current evidence';
const numeric = (v: unknown, digits = 2) => v == null ? missing : f(v, digits);
const percent = (v: unknown) => v == null ? missing : percentage(v);
const basis = (v: unknown) => v == null ? missing : bps(v);
export function agentCounts(t: TerminalState) {
  const a = t.agents;
  const agents = [a.regime, a.toxic_flow, a.execution_quality, a.liquidity_quality, a.perp_crowding, a.predictive_adverse_selection];
  return { available: agents.filter(Boolean).length, unavailable: agents.filter(x => !x).length,
    degraded: agents.filter(x => x && ['DEGRADED', 'ERROR'].includes(x.health)).length };
}
function Reasons({reasons}: {reasons?: string[]}) {
  return reasons?.length ? <ul className="researchReasons">{reasons.map((r, i) => <li key={i}>{r}</li>)}</ul> : <p className="muted">{missing}</p>;
}
// Explicit backend values only; detail labels never invent decision thresholds.
function EvidenceFields({data}: {data: Record<string, unknown> | null | undefined}) {
  if (!data || !Object.keys(data).length) return <p className="muted">{missing}</p>;
  return <dl className="researchDetails">{Object.entries(data).map(([name, value]) => <div key={name}>
    <dt>{name.replaceAll('_', ' ')}</dt><dd>{value == null ? missing : typeof value === 'object'
      ? <pre>{JSON.stringify(value, null, 2)}</pre> : String(value)}</dd>
  </div>)}</dl>;
}
function Card({name, kind, agent, observations, note, details, historical}: {
  name: string; kind: string; agent: (AgentRecommendation & {state: string}) | null;
  observations: Array<[string, ReactNode]>; note: string; details?: ReactNode; historical: boolean;
}) {
  const shadow = name.startsWith('Predictive');
  return <Panel title={name} className={`researchAgent ${shadow ? 'shadowAgentCard' : ''}`} meta={<Badge tone={shadow ? 'blue' : 'neutral'}>{kind}</Badge>}>
    <div className="researchCardBody">
      <div className="researchBadges"><Badge tone={!agent ? 'warn' : ['ERROR', 'DEGRADED'].includes(agent.health) ? 'bad' : agent.health === 'READY' ? 'good' : 'warn'}>{agent?.health ?? 'UNAVAILABLE'}</Badge>
        {agent && <Badge>{agent.state}</Badge>}<Badge>{historical ? 'HISTORICAL' : 'REPORTED OBSERVATION'}</Badge>
        {agent && <Badge tone="blue">{agent.simulated ? 'PAPER / SIMULATED' : 'NORMALIZED EVIDENCE'}</Badge>}</div>
      {shadow && <p className="shadowAuthority">ML SHADOW · OBSERVATIONAL ONLY · NO EXECUTION AUTHORITY · NO QUOTE AUTHORITY</p>}
      <h3>Observation</h3><Metrics items={observations}/><p className="muted">{note}</p>
      <h3>Recommendation</h3>{shadow ? <p className="muted">Observational predictions have no effect on spread, size, levels or execution authorization.</p> : <Metrics items={[
        ['Spread', agent ? `${f(agent.spread_multiplier)}×` : missing], ['BID size', agent ? `${f(agent.bid_size_multiplier)}×` : missing],
        ['ASK size', agent ? `${f(agent.ask_size_multiplier)}×` : missing], ['Maximum levels', agent ? agent.max_levels ?? 'No additional cap' : missing],
      ]}/>}
      <h3>Why · backend reasons</h3><Reasons reasons={agent?.reasons}/>
      <h3>Evidence support</h3><Metrics items={[
        [shadow ? 'Inference support' : 'Reported confidence', shadow ? observations.find(x => x[0] === 'Inference support')?.[1] ?? missing : numeric(agent?.confidence)],
        ['Evidence version', agent?.evidence_version ?? missing], ['Agent version', agent?.version ?? missing],
      ]}/>
      <details><summary>View details · {name}</summary>
        <Metrics items={[["Identity", agent?.agent ?? missing], ["Implementation", agent?.implementation_version ?? missing],
          ['Updated', evidenceTime(agent?.updated_at)], ['Quote influence', shadow ? 'NONE' : agent ? String(agent.affects_quotes) : missing]]}/>
        <p className="muted">Readiness and threshold explanation: only backend reasons above establish rationale. Additional thresholds or validated accuracy are unavailable from current evidence.</p>
        {details}
      </details>
    </div>
  </Panel>;
}
export function AgentDetails({t, historical}: {t: TerminalState; historical: boolean}) {
  const a = t.agents, r = a.regime, tox = a.toxic_flow, eq = a.execution_quality,
    lq = a.liquidity_quality, pc = a.perp_crowding, ml = a.predictive_adverse_selection;
  const evidence = a.evidence as Record<string, unknown> | null;
  // Associated evidence is displayed only when its declared version matches the output.
  const provenance = (agent: AgentRecommendation | null) => <>
    <h3>Data provenance</h3>{agent && evidence?.version === agent.evidence_version ? <EvidenceFields data={evidence}/> : <p className="muted">{missing} · matching input version not published.</p>}
  </>;
  return <div className="researchAgentGrid">
    <Card name="Regime v2" kind="HEURISTIC" agent={r} historical={historical} observations={[
      ['Regime / direction', r ? `${r.state} / ${r.direction}` : missing], ['Momentum', basis(r?.momentum_bps)],
      ['Volatility score', numeric(r?.volatility_score)], ['Funding stress', numeric(r?.funding_stress_score)],
      ['Basis stress', numeric(r?.basis_stress_score)], ['Book pressure', numeric(r?.book_pressure_score)], ['Inventory stress', numeric(r?.inventory_stress_score)],
    ]} note="A trending regime is a market observation, not an instruction to buy or sell." details={<><EvidenceFields data={r ? {realized_volatility: r.realized_volatility, book_imbalance: r.book_imbalance, trend_strength: r.trend_strength} : null}/>{provenance(r)}</>}/>
    <Card name="Toxic Flow v2" kind="DETERMINISTIC" agent={tox} historical={historical} observations={[
      ['BID toxicity', tox && tox.metrics.matured_fills > 0 && Number(tox.metrics.bid_confidence) > 0 ? numeric(tox.metrics.bid_toxic_flow_score) : missing],
      ['ASK toxicity', tox && tox.metrics.matured_fills > 0 && Number(tox.metrics.ask_confidence) > 0 ? numeric(tox.metrics.ask_toxic_flow_score) : missing],
      ['Matured fills', tox?.metrics.matured_fills ?? missing], ['Pending markouts', tox?.metrics.pending_markouts ?? missing],
      ['Mean / median markout', `${basis(tox?.metrics.mean_signed_markout_bps)} / ${basis(tox?.metrics.median_markout_bps)}`],
      ['1s / 5s / 15s', [tox?.metrics.markout_1s_bps, tox?.metrics.markout_5s_bps, tox?.metrics.markout_15s_bps].map(basis).join(' / ')],
      ['Toxicity persistence', tox && tox.metrics.matured_fills > 0 ? percent(tox.metrics.toxicity_persistence) : missing],
    ]} note="Horizon observations can share the same fill; their sample counts are not independent fills. Missing markouts do not establish zero toxicity."
      details={<><EvidenceFields data={tox?.metrics}/>{provenance(tox)}</>}/>
    <Card name="Execution Quality v2" kind="HEURISTIC" agent={eq} historical={historical} observations={[
      ['Fill count', eq?.metrics.fill_count ?? missing], ['Spread capture', basis(eq?.metrics.average_spread_capture_bps)],
      ['Mature markout', basis(eq?.metrics.average_mature_markout_bps)], ['Reconciliation churn', percent(eq?.metrics.reconciliation_churn_ratio)],
      ['Rejected / unknown', eq ? `${eq.metrics.reject_count} / ${eq.metrics.unknown_order_count}` : missing],
      ['First fill / quote lifetime (seconds)', `${numeric(eq?.metrics.mean_time_to_first_fill_seconds)} / ${numeric(eq?.metrics.mean_quote_lifetime_seconds)}`],
    ]} note="PAPER lifecycle measurements are simulated observations. Missing venue acknowledgment or fill measurements remain unavailable."
      details={<><EvidenceFields data={eq?.metrics}/>{provenance(eq)}</>}/>
    <Card name="Liquidity Quality" kind="HEURISTIC" agent={lq} historical={historical} observations={[
      ['BID / ASK depth (base)', `${numeric(lq?.metrics.bid_depth_base)} / ${numeric(lq?.metrics.ask_depth_base)}`],
      ['Spread', basis(lq?.metrics.spread_bps)], ['Thin score', numeric(lq?.metrics.thin_score)],
      ['Instability', numeric(lq?.metrics.instability_score)], ['Imbalance', numeric(lq?.metrics.imbalance_score)],
    ]} note="Book observations describe available liquidity evidence; recommendations remain subordinate to risk and final authorization."
      details={<><EvidenceFields data={lq?.metrics}/>{provenance(lq)}</>}/>
    <Card name="Perp Crowding" kind="HEURISTIC" agent={pc} historical={historical} observations={[
      ['Long / short crowding', `${numeric(pc?.metrics.long_crowding_score)} / ${numeric(pc?.metrics.short_crowding_score)}`],
      ['OI change', pc && pc.metrics.observation_count >= 2 ? percent(pc.metrics.oi_change_ratio) : missing],
      ['Funding rate change', pc && pc.metrics.observation_count >= 2 ? accountingValue(pc.metrics.funding_rate_delta) : missing],
      ['Basis stress', numeric(pc?.metrics.basis_stress_score)], ['Source observations', pc?.metrics.observation_count ?? missing],
    ]} note="A single open-interest observation does not establish a trend. Funding context is not a booked funding payment."
      details={<><EvidenceFields data={pc?.metrics}/>{provenance(pc)}</>}/>
    <Card name="Predictive Adverse Selection" kind="ML SHADOW" agent={ml} historical={historical} observations={[
      ['Inference state', ml?.state ?? missing], ['Inference support', numeric(ml?.metrics.inference_confidence)],
      ['BID adverse probability', percent(ml?.metrics.bid_adverse_probability)], ['ASK adverse probability', percent(ml?.metrics.ask_adverse_probability)],
      ['Horizon (seconds)', numeric(ml?.metrics.markout_horizon_seconds, 0)], ['Feature schema', ml?.feature_schema_version ?? missing],
      ['Model version', ml?.model_provenance?.model_version ?? missing], ['Last inference', evidenceTime(ml?.metrics.last_inference_time)],
    ]} note="Probabilities are conditional on fill. Inference support is not validated prediction accuracy. Unavailable inputs are explained by backend reasons."
      details={<><h3>Model provenance</h3><EvidenceFields data={ml?.model_provenance}/>{provenance(ml)}</>}/>
  </div>;
}
