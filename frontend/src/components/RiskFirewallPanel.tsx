import { useTerminalStore } from "../stores/terminal";
import { terminalEnvelopeFailure } from "../utils/terminalIntegrity";
import type { TerminalState } from "../types";
import { currentSourcePrices } from "../utils/freshness";
import { number as f, bps } from "../utils/format";
const signed = (x: unknown, d = 2) =>
  x == null ? "—" : (Number(x) >= 0 ? "+" : "") + f(x, d);

export function ReferenceSourcesPanel({ t }: { t: TerminalState }) {
  const refs = t.references;
  if (!refs)
    return (
      <section className="panel">
        <div className="panelHead">
          <b>Reference Sources</b>
          <span>Waiting for evidence</span>
        </div>
      </section>
    );
  const order = [
    "REDSTONE",
    "HYPERLIQUID_ORACLE",
    "KRAKEN",
    "COINGECKO",
    "HYPERLIQUID_MID",
    "HYPERLIQUID_MARK",
  ];
  const label: Record<string, string> = {
    REDSTONE: "RedStone · ORACLE",
    HYPERLIQUID_ORACLE: "HL Oracle · NATIVE",
    KRAKEN: "Kraken · EXCHANGE",
    COINGECKO: "CoinGecko · AGGREGATOR",
    HYPERLIQUID_MID: "HL Mid · VENUE",
    HYPERLIQUID_MARK: "HL Mark · PERP",
  };
  return (
    <section className="panel referencePanel">
      <div className="panelHead">
        <b>Reference Sources</b>
        <span>
          Last decision {refs.consensus.confidence_state} · v{refs.version}
        </span>
      </div>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Source</th>
              <th>Price</th>
              <th>Source age now</th>
              <th>Source freshness at emission</th>
              <th>Last provider state / transport</th>
              <th>Last evaluated deviation</th>
              <th>Last decision outlier</th>
            </tr>
          </thead>
          <tbody>
            {order.map((k) => {
              const e = refs.evidence[k];
              return e ? (
                <tr key={k}>
                  <td>
                    {label[k] ?? k}
                    {k === "REDSTONE" && e.transport ? " · " + e.transport : ""}
                  </td>
                  <td>{e.price != null ? "$" + f(e.price) + (e.stale ? " · STALE" : !e.healthy ? " · UNAVAILABLE" : "") : "—"}</td>
                  <td>{e.source_timestamp ? f(e.age_ms, 0) + " ms" : "—"}</td>
                  <td>{e.stale ? "STALE" : e.healthy ? "FRESH AT EMISSION" : "UNAVAILABLE"}</td>
                  <td>
                    <span className="statePill">
                      {e.status}
                      {e.transport ? " · " + e.transport : ""}
                      {e.transport_quality ? " · " + e.transport_quality : ""}
                      {e.simulated ? " · SIM" : ""}
                    </span>
                  </td>
                  <td>{bps(refs.deviations_bps[k])}</td>
                  <td>
                    {refs.consensus.outliers.includes(k) ? "OUTLIER" : "—"}
                  </td>
                </tr>
              ) : null;
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function RiskFirewallPanel({ t }: { t: TerminalState }) {
  const connected = useTerminalStore(s => s.wsState === "connected");
  const current = currentSourcePrices(t, connected && !terminalEnvelopeFailure(t.emitted_at, Date.now()));
  const d = t.risk_firewall?.decision,
    a = t.risk_authorization,
    c = t.reference_consensus;
  const exposure = t.projected_exposure,
    pnl = t.pnl_drawdown;
  return (
    <section className="panel firewallPanel">
      <div className="panelHead">
        <b>Risk Firewall</b>
        <span>{t.risk_firewall?.state ?? "—"}</span>
      </div>
      <div className="riskFirewallGrid">
        <div>
          <span>Last risk decision</span>
          <b>{d?.state ?? t.risk_firewall?.state ?? "—"}</b>
        </div>
        <div>
          <span>Last backend authorization</span>
          <b>{a?.authorized ? "AUTHORIZED" : "BLOCKED"}</b>
        </div>
        <div>
          <span>Consensus (current sources)</span>
          <b>{current.consensus_price != null ? "$" + f(current.consensus_price) : "—"}</b>
        </div>
        <div>
          <span>Last consensus decision</span>
          <b>{c?.confidence_state ?? "—"}</b>
        </div>
        <div>
          <span>Projected Long</span>
          <b>{f(exposure?.projected_long_base, 4)}</b>
        </div>
        <div>
          <span>Projected Short</span>
          <b>{f(exposure?.projected_short_base, 4)}</b>
        </div>
        <div>
          <span>Gross Notional</span>
          <b>{exposure ? "$" + f(exposure.gross_quote_notional, 0) : "—"}</b>
        </div>
        <div>
          <span>Inventory Utilization</span>
          <b>
            {exposure
              ? f(Number(exposure.inventory_utilization) * 100, 1) + "%"
              : "—"}
          </b>
        </div>
        <div>
          <span>Liquidation Distance</span>
          <b>
            {d?.liquidation?.distance_bps != null
              ? f(d.liquidation.distance_bps, 0) + " bps"
              : (d?.liquidation?.status ?? "—")}
          </b>
        </div>
        <div>
          <span>Session PnL</span>
          <b>
            {pnl?.session_pnl != null ? "$" + signed(pnl.session_pnl) : "—"}
          </b>
        </div>
        <div>
          <span>Drawdown</span>
          <b>
            {pnl?.drawdown_pct != null
              ? f(Number(pnl.drawdown_pct) * 100, 2) + "%"
              : "—"}
          </b>
        </div>
        <div>
          <span>Risk Multipliers</span>
          <b>
            {d
              ? f(d.spread_multiplier, 2) +
                "x / " +
                f(d.size_multiplier, 2) +
                "x"
              : "—"}
          </b>
        </div>
      </div>
      <div className="riskReasons">
        <b>Reasons</b>
        {(d?.reasons ?? a?.reasons ?? []).map((x: string, i: number) => (
          <p key={i}>• {x}</p>
        ))}
      </div>
      <div className="riskEvents">
        <b>Recent risk events</b>
        {t.risk_events
          .slice(-5)
          .reverse()
          .map((e, i) => (
            <p key={i}>
              {new Date(e.timestamp).toLocaleTimeString()} · {e.previous_state}{" "}
              → {e.new_state} · {e.reasons.join("; ")}
            </p>
          ))}
      </div>
    </section>
  );
}
