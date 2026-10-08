import type { TerminalState } from "../types";
import { number as f, percentage, timestamp, fingerprint } from "../utils/format";
export function AgentPanel({ t }: { t: TerminalState }) {
  const a = t.agents,
    s = a?.supervisor,
    r = a?.regime,
    tox = a?.toxic_flow,
    eq = a?.execution_quality,
    lq = a?.liquidity_quality,
    pc = a?.perp_crowding,
    ml = a?.predictive_adverse_selection;
  if (!s)
    return (
      <section className="panel agentPanel">
        <div className="panelHead">
          <b>Supervisory Agents</b>
          <span>Waiting for evidence</span>
        </div>
      </section>
    );
  const sim = s.simulated ? " · PAPER / SIMULATED" : "";
  return (
    <section className="panel agentPanel">
      <div className="panelHead">
        <b>Supervisory Agents</b>
        <span>
          v{s.version}
          {sim}
        </span>
      </div>
      <div className="agentGrid">
        <div>
          <small>REGIME V2 · HEURISTIC</small>
          <b>
            {r?.state ?? "—"} · {r?.direction ?? "—"}
          </b>
          <span>
            conf {f(r?.confidence, 2)} · mom {f(r?.momentum_bps, 1)} bps · vol{" "}
            {f(r?.volatility_score, 2)}
          </span>
          <em>
            {f(r?.spread_multiplier, 2)}x spread /{" "}
            {f(r?.bid_size_multiplier, 2)}x size
          </em>
          <span>funding {f(r?.funding_stress_score, 2)} · basis {f(r?.basis_stress_score, 2)} · pressure {f(r?.book_pressure_score, 2)}</span>
        </div>
        <div>
          <small>TOXIC FLOW V2 · DETERMINISTIC</small>
          <b>{tox?.state ?? "—"}</b>
          <span>
            score {f(tox?.metrics.overall_toxic_flow_score, 2)} · bid{" "}
            {f(tox?.metrics.bid_toxic_flow_score, 2)} · ask{" "}
            {f(tox?.metrics.ask_toxic_flow_score, 2)}
          </span>
          <em>
            {tox?.metrics.matured_fills ?? 0} matured ·{" "}
            {tox?.metrics.pending_markouts ?? 0} pending · markout{" "}
            {f(tox?.metrics.mean_signed_markout_bps, 1)} bps
          </em>
          <span>1s {f(tox?.metrics.markout_1s_bps, 1)} · 5s {f(tox?.metrics.markout_5s_bps, 1)} · 15s {f(tox?.metrics.markout_15s_bps, 1)} bps</span>
          <span>median {f(tox?.metrics.median_markout_bps, 1)} · persistence {percentage(tox?.metrics.toxicity_persistence)}</span>
        </div>
        <div>
          <small>EXECUTION QUALITY V2 · HEURISTIC</small>
          <b>{eq?.state ?? "—"}</b>
          <span>
            conf {f(eq?.confidence, 2)} · fills {eq?.metrics.fill_count ?? 0} ·
            capture {f(eq?.metrics.average_spread_capture_bps, 1)} bps
          </span>
          <em>
            markout {f(eq?.metrics.average_mature_markout_bps, 1)} bps · churn{" "}
            {f(Number(eq?.metrics.reconciliation_churn_ratio ?? 0) * 100, 1)}% ·
            reject/unknown {eq?.metrics.reject_count ?? 0}/
            {eq?.metrics.unknown_order_count ?? 0}
          </em>
          <span>first fill {f(eq?.metrics.mean_time_to_first_fill_seconds, 2)} s · lifetime {f(eq?.metrics.mean_quote_lifetime_seconds, 2)} s</span>
        </div>
        <div>
          <small>LIQUIDITY QUALITY · HEURISTIC</small>
          <b>{lq?.state ?? "UNAVAILABLE"} · {lq?.health ?? "UNAVAILABLE"}</b>
          <span>conf {f(lq?.confidence, 2)} · BID depth {f(lq?.metrics.bid_depth_base, 2)} / ASK {f(lq?.metrics.ask_depth_base, 2)} base</span>
          <span>thin {f(lq?.metrics.thin_score, 2)} · instability {f(lq?.metrics.instability_score, 2)} · BBO {f(lq?.metrics.spread_bps, 1)} bps</span>
          <em>{f(lq?.spread_multiplier, 2)}× spread · BID {f(lq?.bid_size_multiplier, 2)}× / ASK {f(lq?.ask_size_multiplier, 2)}× · levels {lq?.max_levels ?? "upstream"}</em>
        </div>
        <div>
          <small>PERP CROWDING · HEURISTIC</small>
          <b>{pc?.state ?? "UNAVAILABLE"} · {pc?.health ?? "UNAVAILABLE"}</b>
          <span>conf {f(pc?.confidence, 2)} · long {f(pc?.metrics.long_crowding_score, 2)} / short {f(pc?.metrics.short_crowding_score, 2)}</span>
          <span>OI change {percentage(pc?.metrics.oi_change_ratio)} · {pc?.metrics.observation_count ?? 0} source observations</span>
          <em>{f(pc?.spread_multiplier, 2)}× spread · BID {f(pc?.bid_size_multiplier, 2)}× / ASK {f(pc?.ask_size_multiplier, 2)}×</em>
        </div>
        <div className="shadowAgentCard">
          <small>ML SHADOW · NO QUOTE AUTHORITY</small>
          <b>{ml?.state ?? "UNAVAILABLE"} · {ml?.health ?? "UNAVAILABLE"}</b>
          <span>mode {ml?.mode ?? "SHADOW"} · evidence support {f(ml?.metrics.inference_confidence, 2)} · v{ml?.version ?? 0}</span>
          <span>BID adverse {percentage(ml?.metrics.bid_adverse_probability)} · ASK adverse {percentage(ml?.metrics.ask_adverse_probability)}</span>
          <span>conditional on fill · {f(ml?.metrics.markout_horizon_seconds, 0)} s target · {ml?.simulated ? "SIMULATED" : "NORMALIZED EVIDENCE"}</span>
          <em>model {ml?.model_provenance?.model_version ?? "unavailable"} · {fingerprint(ml?.model_provenance?.model_sha256)}</em>
          <span>schema {ml?.feature_schema_version ?? "unavailable"} · last inference {timestamp(ml?.metrics.last_inference_time)}</span>
          <p className="muted">Observational predictions have no effect on spread, size, levels or execution authorization.</p>
          {ml?.reasons.map((reason, i) => <p className="muted" key={i}>{reason}</p>)}
        </div>
        <div>
          <small>SUPERVISOR</small>
          <b>{s.enabled ? "ENABLED" : "DISABLED"}</b>
          <span>
            {f(s.spread_multiplier, 2)}x spread · bid{" "}
            {f(s.bid_size_multiplier, 2)}x · ask {f(s.ask_size_multiplier, 2)}x
          </span>
          <em>
            max levels {s.max_levels ?? "—"} · fingerprint{" "}
            {s.fingerprint.slice(0, 12)}…
          </em>
        </div>
      </div>
      <div className="agentDiagnostics">
        {[r, tox, eq, lq, pc].map((agent, i) =>
          agent ? (
            <div key={i}>
              <b>
                {agent.agent} · {agent.health}
              </b>
              <span>
                Confidence {f(agent.confidence)} · v{agent.version} · spread{" "}
                {f(agent.spread_multiplier)}× · BID{" "}
                {f(agent.bid_size_multiplier)}× / ASK{" "}
                {f(agent.ask_size_multiplier)}×
              </span>
              {agent.reasons.map((reason, j) => (
                <p key={j}>{reason}</p>
              ))}
            </div>
          ) : (
            <p key={i}>Agent evidence unavailable</p>
          ),
        )}
      </div>
      <div className="agentReasons">
        {s.reasons.map((x, i) => (
          <p key={i}>• {x}</p>
        ))}
      </div>
    </section>
  );
}
