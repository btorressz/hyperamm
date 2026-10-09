import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Panel } from "./TerminalPrimitives";

type ReferenceObservation = {
  provider: string; symbol: string; role: string; authority: string;
  price: string | null; source_timestamp: string | null; age_ms: number;
  healthy: boolean; stale: boolean; status: string; error: string | null;
  deviations_bps: Record<string, string | null>;
};

export function YahooObservationPanel() {
  const [data, setData] = useState<ReferenceObservation | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let mounted = true;
    const update = async () => {
      try {
        const response = await api.referenceObservations();
        if (mounted) { setData(response.observations.find(x => x.provider === "YAHOO_FINANCE") ?? null); setError(false); }
      } catch { if (mounted) { setData(null); setError(true); } }
    };
    void update();
    const timer = setInterval(() => { void update(); }, 10000);
    return () => { mounted = false; clearInterval(timer); };
  }, []);
  const deviation = data?.deviations_bps.yahoo_vs_core_consensus_bps;
  return <Panel title="Yahoo Finance · Observational Only" meta="Research / local data · Authority NONE">
    <p className="muted">Not execution-authoritative. Not evidence of institutional provider acceptance.</p>
    {error ? <p>Observation diagnostics unavailable.</p> : !data ? <p>Loading observation diagnostics…</p> :
      <div className="riskList">
        <p>Symbol <b>{data.symbol}</b></p>
        <p>Price <b>{data.healthy && data.price != null ? "$" + Number(data.price).toLocaleString() : "Unavailable"}</b></p>
        <p>Source timestamp <b>{data.source_timestamp ?? "—"}</b></p>
        <p>Source age at poll <b>{data.source_timestamp ? data.age_ms + " ms" : "—"}</b></p>
        <p>Status <b>{data.status}{data.stale ? " · STALE" : ""}</b></p>
        <p>Deviation vs core <b>{deviation != null ? Number(deviation).toFixed(2) + " bps" : "—"}</b></p>
        <p>Authority <b>NONE</b></p>
        {data.error ? <p>Diagnostic <b>{data.error}</b></p> : null}
      </div>}
  </Panel>;
}
