import { useEffect, useState, useRef, type ChangeEvent } from "react";
import { api } from "../api/client";
import type { StrategyConfig, TerminalState } from "../types";
export function StrategyControls({ t }: { t: TerminalState }) {
  const [c, setC] = useState<StrategyConfig>(t.strategy.config),
    [msg, setMsg] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const baseline = useRef(JSON.stringify(t.strategy.config)),
    server = JSON.stringify(t.strategy.config),
    dirty = JSON.stringify(c) !== baseline.current;
  const previousServer = useRef(server);
  useEffect(() => {
    if (server !== previousServer.current) {
      previousServer.current = server;
      if (!dirty) {
        baseline.current = server;
        setC(JSON.parse(server));
      }
    }
  }, [server, dirty]);
  const set = (k: keyof StrategyConfig, v: unknown) =>
    setC((x) => ({ ...x, [k]: v }));
  const update = async () => {
    setBusy(true);
    setMsg("");
    setError("");
    try {
      const response = await api.updateStrategy(c);
      baseline.current = JSON.stringify(response.config);
      setC(response.config);
      setMsg("Configuration saved. Backend controls running state.");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const reset = () => {
    baseline.current = server;
    setC(JSON.parse(server));
    setMsg("");
    setError("");
  };
  const input = (key: keyof StrategyConfig, label: string) => (
    <label>
      {label}
      <input
        value={String(c[key])}
        onChange={(e: ChangeEvent<HTMLInputElement>) =>
          set(key, e.target.value)
        }
      />
    </label>
  );
  return (
    <section className="panel controls">
      <div className="panelHead">
        <b>Advanced AMM configuration</b>
        <span>
          {dirty ? "UNSAVED CHANGES" : "Saved configuration"} · server validated
        </span>
      </div>
      <div className="controlGroup">
        <h4>AMM & Execution</h4>
        <div className="formGrid">
          <label>
            Market data
            <select
              value={c.market_data_mode}
              onChange={(e) => set("market_data_mode", e.target.value)}
            >
              <option value="DEMO">DEMO</option>
              <option value="LIVE">LIVE</option>
            </select>
          </label>
          <label>
            Execution
            <select
              value={c.execution_mode}
              onChange={(e) => set("execution_mode", e.target.value)}
            >
              <option value="PAPER">PAPER</option>
              <option value="TESTNET">TESTNET</option>
            </select>
          </label>
          <label>
            AMM Model
            <select
              value={c.amm_model}
              onChange={(e) => set("amm_model", e.target.value)}
            >
              <option>CONSTANT_PRODUCT</option>
              <option>CONCENTRATED</option>
            </select>
          </label>
          <label>
            Levels / side
            <input
              type="number"
              value={c.levels_per_side}
              onChange={(e) => set("levels_per_side", Number(e.target.value))}
            />
          </label>
          {input("market", "Market symbol")}
          {input("max_distance_bps", "Max distance (bps)")}
          {input("total_liquidity", "Liquidity / side")}
          {input("base_order_size", "Base order size")}
          {input("virtual_base_reserve", "Virtual base reserve")}
          {input("virtual_quote_reserve", "Virtual quote reserve")}
          {input("concentration_factor", "Concentration factor")}
          {input("concentration_lower_bps", "Lower bound (bps)")}
          {input("concentration_upper_bps", "Upper bound (bps)")}
          <label>
            Refresh (ms)
            <input
              type="number"
              value={c.quote_refresh_interval_ms}
              onChange={(e) =>
                set("quote_refresh_interval_ms", Number(e.target.value))
              }
            />
          </label>
        </div>
      </div>
      <div className="controlGroup">
        <h4>Inventory-Aware Quoting</h4>
        <div className="formGrid">
          <label>
            Inventory skew
            <select
              value={c.inventory_skew_enabled ? "ENABLED" : "DISABLED"}
              onChange={(e) =>
                set("inventory_skew_enabled", e.target.value === "ENABLED")
              }
            >
              <option>ENABLED</option>
              <option>DISABLED</option>
            </select>
          </label>
          {input("target_inventory_base", "Target inventory")}
          {input("soft_inventory_limit_base", "Soft inventory limit")}
          {input("hard_inventory_limit_base", "Hard inventory limit")}
          {input("max_inventory_price_skew_bps", "Max price skew (bps)")}
          {input("inventory_size_skew_strength", "Size skew strength")}
          {input("min_inventory_size_multiplier", "Min size multiplier")}
          {input("max_inventory_size_multiplier", "Max size multiplier")}
          <label>
            Inventory stale after (s)
            <input
              type="number"
              value={c.inventory_stale_after_seconds}
              onChange={(e) =>
                set("inventory_stale_after_seconds", Number(e.target.value))
              }
            />
          </label>
        </div>
        <small className="controlHint">
          Disabling skew removes price/size bias; hard inventory limits remain
          safety-authoritative.
        </small>
      </div>
      <div className="controlGroup">
        <h4>Market Adaptation</h4>
        <div className="formGrid">
          <label>
            Market adaptation
            <select
              value={c.market_adaptation_enabled ? "ENABLED" : "DISABLED"}
              onChange={(e) =>
                set("market_adaptation_enabled", e.target.value === "ENABLED")
              }
            >
              <option>ENABLED</option>
              <option>DISABLED</option>
            </select>
          </label>
          <label>
            Volatility window
            <input
              type="number"
              value={c.volatility_window_samples}
              onChange={(e) =>
                set("volatility_window_samples", Number(e.target.value))
              }
            />
          </label>
          <label>
            Minimum samples
            <input
              type="number"
              value={c.volatility_min_samples}
              onChange={(e) =>
                set("volatility_min_samples", Number(e.target.value))
              }
            />
          </label>
          {input("volatility_low_threshold", "Volatility low threshold")}
          {input("volatility_high_threshold", "Volatility high threshold")}
          {input("volatility_spread_strength", "Volatility spread strength")}
          {input("volatility_size_strength", "Volatility size strength")}
          <label>
            Book levels
            <input
              type="number"
              value={c.book_imbalance_levels}
              onChange={(e) =>
                set("book_imbalance_levels", Number(e.target.value))
              }
            />
          </label>
          {input("imbalance_spread_strength", "Imbalance spread strength")}
          {input("imbalance_size_strength", "Imbalance size strength")}
          {input("min_spread_multiplier", "Min spread multiplier")}
          {input("max_spread_multiplier", "Max spread multiplier")}
          {input("min_market_size_multiplier", "Min market size multiplier")}
        </div>
        <small className="controlHint">
          Phase 6 widens only and reduces variable liquidity; Phase 5 inventory
          hard limits remain authoritative.
        </small>
      </div>
      <div className="controlGroup">
        <h4>Perpetual Context</h4>
        <div className="formGrid">
          <label>
            Perp context
            <select
              value={c.perp_context_enabled ? "ENABLED" : "DISABLED"}
              onChange={(e) =>
                set("perp_context_enabled", e.target.value === "ENABLED")
              }
            >
              <option>ENABLED</option>
              <option>DISABLED</option>
            </select>
          </label>
          <label>
            Perp stale after (s)
            <input
              type="number"
              value={c.perp_context_stale_after_seconds}
              onChange={(e) =>
                set("perp_context_stale_after_seconds", Number(e.target.value))
              }
            />
          </label>
          {input("perp_mark_weight", "Mark weight")}
          {input("perp_oracle_weight", "Oracle weight")}
          {input(
            "funding_reference_abs_rate",
            "Funding normalization reference",
          )}
          {input("max_funding_reference_shift_bps", "Max funding shift (bps)")}
          {input("max_perp_reference_shift_bps", "Max total perp shift (bps)")}
        </div>
        <small className="controlHint">
          Phase 7 changes strategy reference only. Native mark/oracle/funding/OI
          remain context; deterministic risk stays downstream.
        </small>
      </div>
      <div className="controlGroup">
        <h4>Quote normalization & refresh</h4>
        <div className="formGrid">
          {input("tick_size", "Tick size")}
          {input("size_tolerance", "Size tolerance")}
          {input("replace_tolerance_bps", "Replace tolerance (bps)")}
          <label>
            Size precision
            <input
              type="number"
              value={c.size_precision}
              onChange={(e) => set("size_precision", Number(e.target.value))}
            />
          </label>
        </div>
      </div>
      {c.execution_mode !== t.strategy.config.execution_mode && (
        <p className="alert">
          Execution mode change uses backend TESTNET guards and resets the
          accounting context. Review before saving.
        </p>
      )}
      {(c.market !== t.strategy.config.market ||
        c.market_data_mode !== t.strategy.config.market_data_mode) && (
        <p className="alert">
          Market or data context change resets the accounting session.
          Current-session terminal history will reset.
        </p>
      )}
      {dirty && server !== baseline.current && (
        <p className="alert">
          Server configuration changed while editing. Reset to load current
          values.
        </p>
      )}
      <div className="actions">
        <button className="primary" disabled={busy || !dirty} onClick={update}>
          {busy ? "Saving…" : "Save"}
        </button>
        <button disabled={busy || !dirty} onClick={reset}>
          Reset
        </button>
      </div>
      {msg && (
        <small className="formMsg" role="status">
          {msg}
        </small>
      )}
      {error && (
        <p className="inlineError" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
