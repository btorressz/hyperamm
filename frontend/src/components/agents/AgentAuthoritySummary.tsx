import type { TerminalState } from '../../types';
import { Panel, Metrics } from '../TerminalPrimitives';
import { Badge } from '../Badge';
import { number as f } from '../../utils/format';

export function AgentAuthoritySummary({t, historical}: {t: TerminalState; historical: boolean}) {
  const auth = t.risk_authorization, risk = t.risk_firewall.decision;
  const bound = !!auth.agent_fingerprint && auth.agent_fingerprint === t.agents.agent_fingerprint && auth.agent_version === t.agents.agent_version;
  return <Panel title="Recommendation → risk → authorization → execution" meta="Read-only authority lineage">
    <div className="researchAuthorityGrid">
      <div><h3>Agent recommendation</h3><p>Agents recommend bounded widening, size reduction or level trimming.</p><Badge>{t.agents.supervisor ? 'RECOMMENDATION' : 'UNAVAILABLE'}</Badge></div>
      <div><h3>Risk evaluation</h3><Badge tone={t.risk_firewall.state === 'HALT' ? 'bad' : 'warn'}>{historical ? 'LAST · ' : ''}{t.risk_firewall.state}</Badge>
        <Metrics items={[["Risk spread / size", risk ? `${f(risk.spread_multiplier)}× / ${f(risk.size_multiplier)}×` : 'Unavailable']]}/>
        {risk?.reasons.map((r: string, i: number) => <p key={i}>{r}</p>)}</div>
      <div><h3>Final authorization</h3><Badge tone={historical ? 'warn' : auth.authorized ? 'good' : 'bad'}>{historical ? 'LAST · ' : ''}{auth.authorized ? 'AUTHORIZED' : 'BLOCKED'}</Badge>
        <p>{bound ? 'Reported authorization binds the displayed agent version and fingerprint.' : 'Matching agent authorization lineage unavailable.'}</p>
        {auth.reasons.map((r, i) => <p key={i}>{r}</p>)}</div>
      <div><h3>Execution evidence</h3><Metrics items={[["Reported fills", t.execution_summary.fill_count ?? 'Unavailable'],
        ['Fill history', t.execution_summary.fill_history_available ? 'Available in current observations' : 'Unavailable']]}/>
        <p>{t.vault.mode === 'PAPER' ? 'PAPER observations are simulated.' : 'TESTNET execution evidence may be partial.'} Exact per-agent causal attribution is unavailable.</p></div>
    </div>
    <p className="muted panelNote">Agents recommend. RiskFirewall evaluates. FinalQuoteAuthorization authorizes. OrderManager executes. Enabling the supervisor does not prove a recommendation was applied or an order filled.</p>
    <p className="muted panelNote">Source freshness remains independent: market {t.market.stale ? 'STALE' : 'reported fresh'} · perp {t.perp_context?.stale ? 'STALE' : t.perp_context ? 'reported fresh' : 'unavailable'} · reference confidence {t.reference_consensus?.confidence_state ?? 'unavailable'}. A fresh terminal envelope does not renew source evidence.</p>
    <details className="researchInset"><summary>Inspect authorization identities</summary><dl className="researchDetails">
      {Object.entries({agent_version: auth.agent_version, agent_fingerprint: auth.agent_fingerprint,
        authorization_fingerprint: auth.authorization_fingerprint, quote_fingerprint: auth.quote_fingerprint,
        evidence_fingerprint: auth.evidence_fingerprint}).map(([k,v]) => <div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd><code>{v ?? 'Unavailable from current evidence'}</code></dd></div>)}
    </dl></details>
    <p className="muted panelNote">Agents cannot submit/cancel orders, change risk limits or capital reservations, clear the kill switch, restore suppressed levels, bypass final authorization or mutate accounting.</p>
  </Panel>;
}
