import type { Decimalish, VaultSnapshot } from '../types';
import { Badge } from './Badge';
import { Panel } from './TerminalPrimitives';
import { accountingValue } from '../utils/researchEvidence';
export function accountingNumber(value: Decimalish | null | undefined, percent = false) { return accountingValue(value, percent); }
export function VaultSummary({vault, historical = false}: {vault: VaultSnapshot; historical?: boolean}) {
  const paper = vault.mode === 'PAPER';
  const metric = (items: Array<[string, Decimalish | null, string?]>) => <div className="vaultMetrics">{items.map(([label,value,unit]) => <div className="metric" key={label}>
    <span>{label}</span><strong title={value == null ? 'Unavailable' : String(value)}>{accountingNumber(value,unit === '%')}</strong><small>{unit === '%' ? 'fraction reported by backend' : unit ?? 'quote currency'}</small>
  </div>)}</div>;
  return <Panel title={`Capital overview · ${vault.market}`} className="vaultSummary" meta={<div className="vaultBadges">
    <Badge tone={paper ? 'blue' : 'warn'}>{paper ? 'PAPER / SIMULATED' : `TESTNET / ${vault.accounting_complete}`}</Badge>
    <Badge tone={historical || vault.stale ? 'warn' : vault.error ? 'bad' : vault.accounting_complete === 'COMPLETE' ? 'good' : 'warn'}>{historical ? 'HISTORICAL' : vault.error ? 'ERROR' : vault.stale ? 'STALE' : vault.accounting_complete}</Badge>
  </div>}>
    <p className="muted">{paper ? 'Perpetual research capital. Fees, funding and capital reservations are simulated assumptions.' : 'Partial authoritative account-wide venue equity and market-specific position evidence. Unsupported economics remain unavailable.'}</p>
    {metric([['Vault Equity',vault.equity_quote], ['Starting Capital',vault.initial_equity_quote], ['Settled Capital',vault.settled_capital_quote],
      ['Available Capital',vault.available_capital_quote], ['Reserved Capital',vault.reserved_capital_quote], ['Capital Utilization',vault.capital_utilization,'%'],
      ['Gross Exposure',vault.gross_exposure_quote], ['Net Exposure',vault.net_exposure_quote]])}
    <p className="muted">Settled capital reflects booked economics; equity also includes available unrealized PnL. Reservations are simulated full-notional commitments, not venue margin. Virtual AMM reserves describe mathematical liquidity, not financial balances; this workspace has no custody or money movement authority.</p>
    <details className="researchInset"><summary>Position, high-water and venue evidence</summary>
      {metric([['Position (signed base)',vault.position_base,'base'], ['Average Entry Price',vault.average_entry_price,'quote / base'],
        ['Mark Price',vault.mark_price,'quote / base'], ['Position Value (signed quote)',vault.position_value_quote],
        ['Peak Equity',vault.peak_equity_quote], ['Drawdown (quote)',vault.drawdown_quote], ['Drawdown',vault.drawdown_pct,'%']])}
      {!paper && metric([['Venue Account Margin Used',vault.margin_used_quote], ['Venue Position Margin Used',vault.position_margin_used_quote],
        ['Venue Withdrawable (evidence only)',vault.venue_withdrawable_quote], ['Liquidation Price',vault.liquidation_price,'quote / base']])}
    </details>
    {vault.error && <p className="dangerText" role="alert">{vault.error}</p>}
    <div className="vaultWarnings">{vault.warnings.map((w,i) => <p className="muted" key={i}>{w}</p>)}</div>
  </Panel>;
}
