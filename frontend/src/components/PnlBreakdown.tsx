import type { PnlBreakdownState, VaultSnapshot } from '../types';
import { accountingNumber } from './VaultSummary';
import { Panel } from './TerminalPrimitives';
export function PnlBreakdown({pnl,vault}: {pnl: PnlBreakdownState; vault: VaultSnapshot}) {
  const values = [
    ['Realized Trading PnL',pnl.realized_trading_pnl], ['Unrealized Trading PnL',pnl.unrealized_trading_pnl],
    ['Gross PnL',pnl.gross_trading_pnl], ['Fees (cost)',vault.fees_quote], ['Funding (signed cash flow)',pnl.funding_pnl],
    ['Net Realized PnL',pnl.net_realized_pnl], ['Net PnL',pnl.net_pnl], ['Session PnL',pnl.session_pnl],
    ['Peak Equity',vault.peak_equity_quote], ['Drawdown (quote)',vault.drawdown_quote],
  ] as const;
  return <Panel title="PnL overview" className="vaultPnl" meta="Backend accounting · quote currency">
    <div className="vaultMetrics">{values.map(([label,value]) => <div className="metric" key={label}><span>{label}</span><strong title={value == null ? 'Unavailable' : String(value)}>{accountingNumber(value)}</strong></div>)}</div>
    <p className="muted">Realized trading PnL comes from closed exposure. Unrealized PnL marks remaining exposure and can change before settlement. Net PnL = realized + unrealized − fees + funding. Positive funding is received; negative funding is paid.</p>
    <p className="muted">Values and formulas come from the accounting service. Missing economics remain unavailable. TESTNET session equity change is not reconciled trading PnL.</p>
    <p className="muted">Fee source: {vault.fee_source} · Funding source: {vault.funding_source}</p>
  </Panel>;
}
