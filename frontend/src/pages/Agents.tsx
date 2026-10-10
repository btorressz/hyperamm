import type { TerminalState } from '../types';
import { AgentPanel } from '../components/AgentPanel';
import { agentCounts } from '../components/agents/AgentDetails';
import { AgentAuthoritySummary } from '../components/agents/AgentAuthoritySummary';
import { AgentEvents } from '../components/agents/AgentEvents';
import { Panel, Metrics, StatusBanner } from '../components/TerminalPrimitives';
import { Badge } from '../components/Badge';
import { number as f } from '../utils/format';
import { evidenceTime } from '../utils/researchEvidence';
import '../phase1331.css';

export function Agents({t, historical = false}: {t: TerminalState; historical?: boolean}) {
  const s = t.agents.supervisor, counts = agentCounts(t);
  return <div className="researchWorkspace stack">
    <div className="researchPageTitle"><div><h1>Agent intelligence workspace</h1><p className="muted">Observations, reasoning and conservative recommendations</p></div><Badge tone={historical ? 'warn' : 'blue'}>{historical ? 'HISTORICAL SNAPSHOT' : 'REPORTED EVIDENCE'}</Badge></div>
    {historical && <StatusBanner>Historical agent output · last-known recommendations and authorization are not current trading authority.</StatusBanner>}
    <Panel title="Supervisor overview" meta={<Badge tone={s ? 'blue' : 'warn'}>{s ? s.enabled ? 'ENABLED' : 'DISABLED' : 'UNAVAILABLE'}</Badge>}>
      <Metrics items={[
        ['Available agents', `${counts.available} / 6`], ['Degraded / error', counts.degraded], ['Missing evidence', counts.unavailable],
        ['Spread recommendation', s ? `${f(s.spread_multiplier)}×` : 'Unavailable'],
        ['BID / ASK size', s ? `${f(s.bid_size_multiplier)}× / ${f(s.ask_size_multiplier)}×` : 'Unavailable'],
        ['Maximum recommended levels', s ? s.max_levels ?? 'No additional cap' : 'Unavailable'],
        ['Agent / reference version', `${t.agents.agent_version} / ${s?.reference_version ?? 'Unavailable'}`],
        ['Supervisor updated', evidenceTime(s?.updated_at)],
      ]}/>
      <p className="muted panelNote">Available counts indicate published outputs, not READY health. Missing outputs are distinct from reported ERROR. Recommendations do not establish executed trades.</p>
      <ul className="researchReasons">{s?.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
      <details className="researchInset"><summary>Supervisor provenance</summary><code>{s?.fingerprint ?? 'Unavailable from current evidence'}</code></details>
    </Panel>
    <AgentAuthoritySummary t={t} historical={historical}/>
    <AgentPanel t={t} workspace historical={historical}/>
    <AgentEvents key={`${t.process_id}:${t.session_id}`} t={t} historical={historical}/>
  </div>;
}
