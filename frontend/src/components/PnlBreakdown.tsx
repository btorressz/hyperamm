import type {PnlBreakdownState, VaultSnapshot} from '../types'
import {accountingNumber} from './VaultSummary'

export function PnlBreakdown({pnl, vault}: {pnl: PnlBreakdownState, vault: VaultSnapshot}) {
  const values = [
    ['Realized Trading PnL', pnl.realized_trading_pnl], ['Unrealized Trading PnL', pnl.unrealized_trading_pnl],
    ['Gross PnL', pnl.gross_trading_pnl], ['Fees (cost)', vault.fees_quote],
    ['Funding (signed cash flow)', pnl.funding_pnl], ['Net Realized PnL', pnl.net_realized_pnl],
    ['Net PnL', pnl.net_pnl], ['Session PnL', pnl.session_pnl],
  ] as const
  return <section className="panel vaultPnl"><div className="panelHead"><b>PnL Breakdown</b><span>Quote currency</span></div>
    <div className="vaultMetrics">{values.map(([label, value]) => <div className="metric" key={label}>
      <span>{label}</span><strong>{accountingNumber(value)}</strong>
    </div>)}</div>
    <p className="muted">Net PnL = realized + unrealized − fees + funding. Positive funding is received; negative funding is paid.</p>
    <p className="muted">Fee source: {vault.fee_source} · Funding source: {vault.funding_source}</p>
  </section>
}
