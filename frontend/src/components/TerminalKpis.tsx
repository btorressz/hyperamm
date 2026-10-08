import type { TerminalState } from "../types";
import { money, quantity, percentage } from "../utils/format";
export function TerminalKpis({ t }: { t: TerminalState }) {
  const v = t.vault;
  const items = [
    ["Position", quantity(v.position_base)],
    ["Vault equity", money(v.equity_quote)],
    ["Session net PnL", money(v.net_pnl_quote)],
    ["Inventory ratio", percentage(t.inventory?.inventory_ratio)],
    ["Capital utilization", percentage(v.capital_utilization)],
    ["Last risk decision", t.risk_firewall.state],
    [
      "Filled notional / fills",
      money(t.execution_summary.filled_notional) +
        " / " +
        (t.execution_summary.fill_count ?? "—"),
    ],
  ];
  return (
    <div className="metrics terminalKpis">
      {items.map(([label, value]) => (
        <div className="metric" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
