import type { TerminalState } from '../../types';
import { Panel, Metrics } from '../TerminalPrimitives';
import { evidenceTime } from '../../utils/researchEvidence';
import { fingerprint } from '../../utils/format';
export function AccountingProvenance({t}: {t: TerminalState}) {
  const v = t.vault;
  return <Panel title="Accounting provenance" className="vaultProvenance" meta="Session evidence · not persistent recovery">
    <Metrics items={[
      ['Accounting version',v.accounting_version], ['Accounting fingerprint',fingerprint(v.accounting_fingerprint)],
      ['Ledger version',v.ledger_version], ['Ledger fingerprint',fingerprint(v.ledger_fingerprint)],
      ['Updated',evidenceTime(v.updated_at)], ['Source / completeness',`${v.source} / ${v.accounting_complete}`],
      ['Reservation source',v.reservation_source],
    ]}/>
    <details className="researchInset"><summary>Inspect full accounting identities</summary><dl className="researchDetails">
      {Object.entries({process_id:t.process_id,session_id:t.session_id,accounting_fingerprint:v.accounting_fingerprint,ledger_fingerprint:v.ledger_fingerprint}).map(([name,value]) => <div key={name}><dt>{name.replaceAll('_',' ')}</dt><dd><code>{value}</code></dd></div>)}
    </dl></details>
    <p className="muted panelNote">Ledger REST has no terminal session ID. Matching mode, market, version and fingerprint plus client connection/session checks cannot establish a cryptographic session binding. In-memory fingerprints do not provide multi-session recovery.</p>
    <div className="vaultEvents">{t.accounting.events.map((event,index) => <p className="muted" key={index}><b>{event.category}</b> · {evidenceTime(event.timestamp)} · {event.message}</p>)}</div>
  </Panel>;
}
