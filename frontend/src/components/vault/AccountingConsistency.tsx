import type { VaultSnapshot } from '../../types';
import { Badge } from '../Badge';
import { Panel, Metrics } from '../TerminalPrimitives';
import { evidenceTime } from '../../utils/researchEvidence';
export function AccountingConsistency({vault,historical}: {vault: VaultSnapshot; historical: boolean}) {
  const c = vault.execution_accounting, authoritative = c.status !== 'UNAVAILABLE' && c.execution_accounting_consistent !== null;
  return <Panel title="Execution ↔ accounting consistency" meta={<Badge tone={historical ? 'warn' : c.status === 'CONSISTENT' ? 'good' : c.status === 'DIVERGED' ? 'bad' : 'warn'}>{historical ? 'LAST · ' : ''}{c.status}</Badge>}>
    <Metrics items={[
      ['Execution fill count',authoritative ? c.execution_fill_count ?? 'Unavailable' : 'Not authoritative'],
      ['Accounted fill count',authoritative ? c.accounted_fill_count ?? 'Unavailable' : 'Not authoritative'],
      ['Unaccounted fill count',authoritative ? c.unaccounted_fill_count ?? 'Unavailable' : 'Not authoritative'],
      ['Oldest unaccounted fill',evidenceTime(c.oldest_unaccounted_fill_at)], ['Latest unaccounted fill',evidenceTime(c.latest_unaccounted_fill_at)],
    ]}/>
    <p className={`${c.status === 'DIVERGED' ? 'dangerText' : 'muted'} panelNote`} role={c.status === 'DIVERGED' ? 'alert' : 'status'}>{c.reason ?? 'No consistency reason reported.'}</p>
    <p className="muted panelNote">Backend-reported status; an empty ledger does not establish consistency. This read-only panel cannot replay fills, repair accounting, change fingerprints or resume trading.</p>
  </Panel>;
}
