import { YahooObservationPanel } from "../components/YahooObservationPanel";
import { ControlActions } from "../components/QuickStrategyControl";
import { Panel, Metrics } from "../components/TerminalPrimitives";
import { percentage, fingerprint, timestamp } from "../utils/format";
import type { TerminalState } from "../types";
import {
  ReferenceSourcesPanel,
  RiskFirewallPanel,
} from "../components/RiskFirewallPanel";
export function Risk({ t, historical }: { t: TerminalState; historical: boolean }) {
  return (
    <>
      <section className="panel pagePanel">
        <div className="panelHead">
          <b>Risk Management</b>
          <span>{historical ? "STALE · LAST SNAPSHOT" : "Phase 8 deterministic authority"}</span>
        </div>
        {historical && <p className="muted">
          Risk and authorization evidence was captured at <time dateTime={t.emitted_at}>{timestamp(t.emitted_at)}</time>.
          {" "}Waiting for a fresh terminal snapshot from the current session.
        </p>}
        <div className="riskHero">
          <div>
            <small>{historical ? "Last manual kill status" : "Manual kill switch"}</small>
            <strong
              className={t.risk.kill_switch_active ? "dangerText" : "bidText"}
            >
              {t.risk.kill_switch_active ? "ACTIVE" : "READY"}
            </strong>
          </div>
          <ControlActions t={t} historical={historical} />
        </div>
        <div className="riskList">
          <p>
            Quote health <b>{t.strategy.quote_health}</b>
          </p>
          <p>
            Automatic firewall state <b>{t.risk_firewall.state}</b>
          </p>
          <p>
            {historical ? "Last final authorization" : "Final authorization"}{" "}
            <b>{t.risk_authorization.authorized ? "AUTHORIZED" : "BLOCKED"}</b>
          </p>
          <p>
            Max order size <b>{String(t.risk.max_order_size)}</b>
          </p>
          <p>
            Max aggregate notional{" "}
            <b>${String(t.risk.max_aggregate_notional)}</b>
          </p>
        </div>
        <p className="muted">
          Manual kill never auto-recovers. Phase 8 automatic HALT may recover
          only through configured hysteresis and healthy confirmations.
        </p>
      </section>
      <Panel title="Capital & authorization" meta={historical ? "LAST SNAPSHOT" : "Phase 11.1 consistency"}>
        <Metrics
          items={[
            ["Capital utilization", percentage(t.vault.capital_utilization)],
            ["Vault drawdown", percentage(t.vault.drawdown_pct)],
            ["Accounting consistency", t.vault.execution_accounting.status],
            [
              "Final authorization envelope",
              fingerprint(t.risk_authorization.authorization_fingerprint),
            ],
          ]}
        />
        <div className="riskGauges">
          {[
            [
              "Inventory utilization",
              t.projected_exposure?.inventory_utilization,
            ],
            ["Capital utilization", t.vault.capital_utilization],
            ["Drawdown", t.vault.drawdown_pct],
          ].map(([label, value]) => (
            <label key={String(label)}>
              {String(label)} · {percentage(value)}
              {value != null && (
                <meter
                  aria-label={String(label)}
                  min={0}
                  max={1}
                  value={Number(value)}
                />
              )}
            </label>
          ))}
        </div>
      </Panel>
      <div className="grid midGrid">
        <ReferenceSourcesPanel t={t} />
        <RiskFirewallPanel t={t} historical={historical} />
      </div>
      <YahooObservationPanel />
    </>
  );
}
