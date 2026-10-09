import { useTerminalStore } from "../stores/terminal";
import { envelopeAgeMs, terminalEnvelopeFailure } from "../utils/terminalIntegrity";
import { Panel, Metrics } from "./TerminalPrimitives";
export function TerminalDiagnostics({ nowMs }: { nowMs: number }) {
  const s = useTerminalStore(), t = s.terminal;
  const age = t ? envelopeAgeMs(t.emitted_at, nowMs) : null;
  const current = s.wsState === "connected" && age !== null && t !== null && !terminalEnvelopeFailure(t.emitted_at, nowMs);
  const short = (id: string | undefined) => id ? id.slice(0, 8) : "—";
  return <Panel title="Terminal observation" meta={current ? "CURRENT · OBSERVATIONAL" : "HISTORICAL / WAITING"}>
    <Metrics items={[
      ["Connection", s.wsState.toUpperCase()],
      ["Envelope", age === null ? "WAITING" : `${current ? "FRESH" : "HISTORICAL"} · ${(age / 1000).toFixed(1)}s${age < 0 ? " (clock skew)" : " old"}`],
      ["Process / session", `${short(t?.process_id)} / ${short(t?.session_id)}`],
      ["Last accepted", s.lastValidFrameAt === null ? "—" : new Date(s.lastValidFrameAt).toLocaleTimeString()],
      ["Sequence", s.lastSequence ?? "—"],
      ["Reconnect attempts", s.reconnectAttempts],
      ["Rejected stale / future / replay", `${s.rejectedFrames.stale} / ${s.rejectedFrames.future} / ${s.rejectedFrames.replay}`],
      ["Rejected schema / order / time", `${s.rejectedFrames.schema} / ${s.rejectedFrames.sequence} / ${s.rejectedFrames.timeRegression}`],
      ["Market evidence at emission", t ? (t.market.stale ? "STALE" : t.system_health.subsystems.market_feed?.status ?? "UNAVAILABLE") : "—"],
    ]} />
    {s.payloadError && <p className="dangerText panelNote">{s.payloadError}</p>}
    {s.connectionNotice && <p className="muted panelNote">Last recovery: {s.connectionNotice}</p>}
  </Panel>;
}
