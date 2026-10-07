import type {Decimalish, VaultSnapshot} from '../types'
import {Badge} from './Badge'

export function accountingNumber(value: Decimalish | null, percent = false) {
  if (value === null) return 'Unavailable'
  const number = Number(value) * (percent ? 100 : 1)
  return Number.isFinite(number)
    ? `${number.toLocaleString(undefined, {maximumFractionDigits: percent ? 3 : 4})}${percent ? '%' : ''}`
    : 'Unavailable'
}

export function VaultSummary({vault}: {vault: VaultSnapshot}) {
  const paper = vault.mode === 'PAPER'
  const metrics: Array<[string, Decimalish | null, boolean?]> = [
    ['Vault Equity', vault.equity_quote], ['Starting Capital', vault.initial_equity_quote],
    ['Settled Capital', vault.settled_capital_quote], ['Available Capital', vault.available_capital_quote],
    ['Reserved Capital', vault.reserved_capital_quote], ['Capital Utilization', vault.capital_utilization, true],
    ['Position (signed base)', vault.position_base], ['Average Entry Price', vault.average_entry_price],
    ['Mark Price', vault.mark_price], ['Position Value (signed quote)', vault.position_value_quote],
    ['Peak Equity', vault.peak_equity_quote], ['Drawdown (quote)', vault.drawdown_quote],
    ['Drawdown', vault.drawdown_pct, true], ['Gross Exposure', vault.gross_exposure_quote],
    ['Net Exposure', vault.net_exposure_quote],
  ]
  return <section className="panel vaultSummary">
    <div className="panelHead"><b>Vault · {vault.market}</b><div className="vaultBadges">
      <Badge tone={paper ? 'blue' : 'warn'}>{paper ? 'PAPER / SIMULATED' : `TESTNET / ${vault.accounting_complete}`}</Badge>
      {!paper && <Badge>AUTHORITATIVE EVIDENCE</Badge>}
      <Badge tone={vault.stale || vault.error ? 'bad' : 'good'}>{vault.error ? 'ERROR' : vault.stale ? 'STALE' : vault.accounting_complete}</Badge>
    </div></div>
    <p className="muted">{paper ? 'Perpetual research capital. Fees, funding and capital reservations are simulated assumptions.' : 'Account-wide venue equity and market-specific position evidence. Unsupported economics remain unavailable.'}</p>
    <div className="vaultMetrics">{metrics.map(([label, value, percent]) => <div className="metric" key={label}>
      <span>{label}</span><strong>{accountingNumber(value, percent)}</strong>
    </div>)}</div>
    {!paper && <div className="vaultMetrics">{[
      ['Venue Account Margin Used', vault.margin_used_quote], ['Venue Position Margin Used', vault.position_margin_used_quote], ['Venue Withdrawable', vault.venue_withdrawable_quote],
      ['Liquidation Price', vault.liquidation_price],
    ].map(([label, value]) => <div className="metric" key={String(label)}><span>{label}</span><strong>{accountingNumber(value)}</strong></div>)}</div>}
    {vault.error && <p className="dangerText" role="alert">{vault.error}</p>}
    <div className="vaultWarnings">{vault.warnings.map(warning => <p className="muted" key={warning}>{warning}</p>)}</div>
  </section>
}
