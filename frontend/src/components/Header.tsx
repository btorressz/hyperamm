import { terminalEnvelopeFailure } from "../utils/terminalIntegrity";
import { useState } from "react";
import { Badge } from "./Badge";
import { api } from "../api/client";
import { price, percentage, quantity } from "../utils/format";
import type { TerminalState } from "../types";
import { currentSourcePrices } from "../utils/freshness";
export function Header({ t, ws }: { t: TerminalState | null; ws: string }) {
  const [error, setError] = useState("");
  const kill = async () => {
    try {
      await api.kill();
      setError("");
    } catch (e) {
      setError(String(e));
    }
  };
  const observationCurrent = ws === "connected" && !!t && !terminalEnvelopeFailure(t.emitted_at, Date.now());
  const current = currentSourcePrices(t, observationCurrent);
  const p = !observationCurrent || t?.perp_context?.stale ? null : t?.perp_context;
  return (
    <header className="topbar">
      <div className="headerMarket">
        <div className="eyebrow">PERPETUAL MARKET</div>
        <div className="marketTitle">
          {t?.market.market ?? "—"}-PERP{" "}
          <span>{price(t?.market.mid_price)}</span>
        </div>
      </div>
      <div className="headerContext">
        <div>
          <small>Mark</small>
          <b>{price(current.mark_price)}</b>
        </div>
        <div>
          <small>HL Oracle</small>
          <b>{price(current.oracle_price)}</b>
        </div>
        <div>
          <small>Funding</small>
          <b>{percentage(p?.funding_rate, 4)}</b>
        </div>
        <div>
          <small>OI · base</small>
          <b>{quantity(p?.open_interest_base)}</b>
        </div>
      </div>
      <div className="headerBadges">
        <Badge tone={ws === "connected" ? "good" : "warn"}>
          TERMINAL {ws.toUpperCase()}
        </Badge>
        <Badge tone={t?.market.mode === "LIVE" ? "blue" : "warn"}>
          {t?.market.mode ?? "UNAVAILABLE"}
        </Badge>
        <Badge tone="blue">
          {t?.strategy.config.execution_mode === "TESTNET"
            ? "GUARDED TESTNET"
            : (t?.strategy.config.execution_mode ?? "—")}
        </Badge>
        <Badge tone={t?.strategy.running ? "good" : "neutral"}>
          {t?.strategy.running ? "RUNNING" : "STOPPED"}
        </Badge>
        <Badge tone={t?.risk_firewall.state === "HALT" ? "bad" : "warn"}>
          RISK {t?.risk_firewall.state ?? "—"}
        </Badge>
        <button
          className="dangerBtn headerKill"
          aria-label="Immediately activate manual kill switch"
          disabled={!t || t.risk.kill_switch_active}
          onClick={kill}
        >
          {t?.risk.kill_switch_active ? "KILL ACTIVE" : "KILL SWITCH"}
        </button>
      </div>
      {error && (
        <span className="inlineError" role="alert">
          {error}
        </span>
      )}
    </header>
  );
}
