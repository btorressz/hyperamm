import { useState } from 'react';
import type { AccountingLedgerState, LedgerEntry } from '../types';
import { accountingNumber as f } from './VaultSummary';
import { Panel, Empty } from './TerminalPrimitives';
import { evidenceTime } from '../utils/researchEvidence';
export type LedgerFilters = {event: string; side: string; source: string; simulation: string};
export function selectLedger(entries: readonly LedgerEntry[], filters: LedgerFilters) {
  return entries.slice(0,100).filter(e => (filters.event === 'ALL' || e.event_type === filters.event) &&
    (filters.side === 'ALL' || (e.side ?? 'NONE') === filters.side) &&
    (filters.source === 'ALL' || e.source === filters.source) &&
    (filters.simulation === 'ALL' || (e.simulated ? 'SIMULATED' : 'NON_SIMULATED') === filters.simulation));
}
export function LedgerDetails({entry}: {entry: LedgerEntry}) {
  return <dl className="researchDetails ledgerDetails">{Object.entries(entry).map(([name,value]) => <div key={name}>
    <dt>{name.replaceAll('_',' ')}</dt><dd><code>{value === null ? 'Unavailable from current evidence' : String(value)}</code></dd>
  </div>)}</dl>;
}
export function AccountingLedger({ledger,mode}: {ledger: AccountingLedgerState | undefined; mode: string}) {
  const [filters,setFilters] = useState<LedgerFilters>({event:'ALL',side:'ALL',source:'ALL',simulation:'ALL'});
  const entries = ledger ? selectLedger(ledger.entries,filters) : [];
  const options = (field: keyof LedgerFilters, values: string[], label: string) => <label>{label}<select value={filters[field]} onChange={e => setFilters({...filters,[field]:e.target.value})}>
    <option value="ALL">All</option>{values.map(v => <option key={v}>{v}</option>)}
  </select></label>;
  return <Panel title="Accounting ledger" className="vaultLedger" meta={`Latest 100 · source order: newest first · version ${ledger?.ledger_version ?? 'Unavailable'}`}>
    <div className="researchFilters">
      {options('event',[...new Set(ledger?.entries.map(e => e.event_type) ?? [])],'Ledger event type')}
      {options('side',['BID','ASK','NONE'],'Ledger side')}
      {options('source',[...new Set(ledger?.entries.map(e => e.source) ?? [])],'Ledger source')}
      {options('simulation',['SIMULATED','NON_SIMULATED'],'Ledger simulation')}
      <button type="button" onClick={() => setFilters({event:'ALL',side:'ALL',source:'ALL',simulation:'ALL'})}>Clear ledger filters</button>
    </div>
    {!ledger ? <Empty>Current ledger evidence is unavailable.</Empty> : <>
      <div className="tableWrap" tabIndex={0} role="region" aria-label="Accounting ledger table; scroll horizontally for all columns"><table><caption className="srOnly">Read-only ledger in backend sequence order. Financial deltas are quote currency unless labeled base.</caption><thead><tr>
        <th scope="col">Seq / Time / Details</th><th scope="col">Type / Market</th><th scope="col">Side / Qty base / Price</th><th scope="col">Capital Δ</th><th scope="col">Position Δ base</th>
        <th scope="col">Fee</th><th scope="col">Funding</th><th scope="col">Realized Δ</th><th scope="col">Position base / Avg entry</th><th scope="col">Source</th>
      </tr></thead><tbody>{entries.map(e => <tr key={`${e.sequence}:${e.event_id}`}>
        <td>{e.sequence}<small><time dateTime={e.timestamp}>{evidenceTime(e.timestamp)}</time></small><details><summary>View ledger entry {e.sequence}</summary><LedgerDetails entry={e}/></details></td>
        <td>{e.event_type}<small>{e.market}</small></td><td>{e.side ?? '—'}<small>{f(e.size)} / {f(e.price)}</small></td>
        <td className="financial">{f(e.cash_delta_quote)}</td><td className="financial">{f(e.position_delta_base)}</td><td className="financial">{f(e.fee_delta_quote)}</td><td className="financial">{f(e.funding_delta_quote)}</td>
        <td className="financial">{f(e.realized_pnl_delta)}</td><td className="financial">{f(e.position_base)}<small>{f(e.average_entry_price)}</small></td>
        <td>{e.source}<small>{e.simulated ? 'SIMULATED' : 'NON-SIMULATED SOURCE'}</small></td>
      </tr>)}{!entries.length && <tr><td colSpan={10} className="emptyCell">{ledger.entries.length ? 'No retained entries match these filters.' : mode === 'TESTNET' ? 'Complete authoritative TESTNET fill accounting is unavailable.' : 'No accounting events have been booked in this research session.'}</td></tr>}</tbody></table></div>
      <p className="muted">Showing {entries.length} of {ledger.entries.length} loaded rows. Client filters preserve authoritative sequence order and cannot change the ledger.</p>
    </>}
    <p className="muted">Append-only session ledger · {ledger?.retention_policy ?? 'Retention evidence unavailable'}. Bounded in-memory history; not an exchange balance or permanent audit archive.</p>
  </Panel>;
}
