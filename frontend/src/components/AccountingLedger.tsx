import type {AccountingLedgerState} from '../types'
import {accountingNumber as f} from './VaultSummary'

export function AccountingLedger({ledger, mode}: {ledger: AccountingLedgerState | undefined, mode: string}) {
  return <section className="panel vaultLedger"><div className="panelHead"><b>Accounting Ledger</b><span>Latest 100 · newest first · version {ledger?.ledger_version ?? '—'}</span></div>
    <div className="tableWrap"><table><thead><tr>
      <th>Seq / Time</th><th>Type / Market</th><th>Side / Qty / Price</th><th>Capital Δ</th>
      <th>Position Δ</th><th>Fee</th><th>Funding</th><th>Realized Δ</th><th>Position / Avg Entry</th><th>Source</th>
    </tr></thead><tbody>{ledger?.entries.map(entry => <tr key={entry.sequence}>
      <td>{entry.sequence}<small>{new Date(entry.timestamp).toLocaleString()}</small></td>
      <td>{entry.event_type}<small>{entry.market}</small></td>
      <td>{entry.side ?? '—'}<small>{entry.size === null ? '—' : f(entry.size)} / {entry.price === null ? '—' : f(entry.price)}</small></td>
      <td>{f(entry.cash_delta_quote)}</td><td>{f(entry.position_delta_base)}</td><td>{f(entry.fee_delta_quote)}</td>
      <td>{f(entry.funding_delta_quote)}</td><td>{f(entry.realized_pnl_delta)}</td>
      <td>{f(entry.position_base)}<small>{f(entry.average_entry_price)}</small></td>
      <td>{entry.source}<small>{entry.simulated ? 'SIMULATED' : 'AUTHORITATIVE'}</small></td>
    </tr>)}{!ledger?.entries.length && <tr><td colSpan={10} className="emptyCell">{mode === 'TESTNET' ? 'Complete authoritative TESTNET fill ledger unavailable.' : 'No accounting events booked in this research session.'}</td></tr>}</tbody></table></div>
    <p className="muted">Append-only session ledger · {ledger?.retention_policy ?? 'HALT_WHEN_FULL'}. History is retained until the session capacity is reached.</p>
  </section>
}
