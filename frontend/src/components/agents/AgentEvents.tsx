import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useResearchSession } from '../../hooks/useResearchSession';
import type { AgentEvent, TerminalState } from '../../types';
import { agentNames, checkedAgentEvents, evidenceTime, type AgentName } from '../../utils/researchEvidence';
import { Panel, Empty } from '../TerminalPrimitives';

export function AgentEventList({events}: {events: AgentEvent[]}) {
  return events.length ? <ol className="researchEventList">{[...events].reverse().map((e,i) => <li key={`${e.agent}:${e.version}:${e.timestamp}:${i}`}>
    <div><strong>{e.agent}</strong> · {e.previous_state ?? 'Initial observation'} → <strong>{e.new_state}</strong> · agent v{e.version}</div>
    <time dateTime={e.timestamp}>{evidenceTime(e.timestamp)}</time>
    <ul>{e.reasons.map((reason, j) => <li key={j}>{reason}</li>)}</ul>
  </li>)}</ol> : <Empty>No retained agent events match this selection.</Empty>;
}
export function AgentEvents({t, historical}: {t: TerminalState; historical: boolean}) {
  const [agent, setAgent] = useState<AgentName | ''>('');
  const session = useResearchSession(t, historical);
  const events = useQuery({
    queryKey: ['agent-events', t.process_id, t.session_id, session.epoch, agent],
    queryFn: async ({signal}) => {
      session.check();
      const response = await api.agentEvents(agent || undefined, 100, signal);
      session.check();
      return checkedAgentEvents(response, agent || undefined, 100);
    },
    enabled: session.enabled, gcTime: 0, retry: false,
    refetchOnWindowFocus: false,
  });
  const snapshotEvents = checkedAgentEvents(t.agent_events, agent || undefined, 20);
  return <Panel title="Agent events" meta="Bounded retained observations · separate from executions">
    <div className="researchFilters"><label>Agent event filter<select value={agent} onChange={e => setAgent(e.target.value as AgentName | '')}>
      <option value="">All agents</option>{agentNames.map(name => <option key={name}>{name}</option>)}
    </select></label><button type="button" disabled={!session.enabled || events.isFetching} onClick={() => void events.refetch()}>Refresh retained events</button></div>
    {historical || !session.enabled ? <><p className="muted panelNote">Historical terminal events · last accepted snapshot only.</p><AgentEventList events={snapshotEvents}/></>
      : events.isError ? <p className="inlineError" role="alert">Agent events could not be loaded: {String(events.error.message)}</p>
      : events.isPending ? <p className="muted panelNote" role="status">Loading recent retained agent events…</p>
      : <AgentEventList events={events.data}/>}
    <p className="muted panelNote">Latest 100 requested; backend retention is at most 250. This is not a permanent audit record. REST events carry no process/session identity; client transition checks reduce stale attribution but cannot prove a wire-level session binding. Refresh is observational and does not execute trades.</p>
  </Panel>;
}
