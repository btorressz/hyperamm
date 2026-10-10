import type { TerminalState } from "../../types";
import { Panel, Empty } from "../TerminalPrimitives";
import { Badge } from "../Badge";
import { accountingValue, evidenceTime } from "../../utils/researchEvidence";

const roles: Record<string, string> = {
  REDSTONE: "Primary external oracle",
  HYPERLIQUID_ORACLE: "Native oraclePx",
  KRAKEN: "Independent exchange reference",
  COINGECKO: "Tertiary aggregate",
  YAHOO_FINANCE: "Observational only · authority NONE",
  HYPERLIQUID_MID: "Execution venue midpoint · comparison evidence",
  HYPERLIQUID_MARK: "Perpetual mark · comparison evidence",
};
export function ProviderHealthSummary({
  t,
  historical,
}: {
  t: TerminalState;
  historical: boolean;
}) {
  const evidence = Object.entries(t.references?.evidence ?? {});
  const hierarchy = Object.keys(roles);
  evidence.sort(
    ([a], [b]) =>
      (hierarchy.includes(a) ? hierarchy.indexOf(a) : hierarchy.length) -
      (hierarchy.includes(b) ? hierarchy.indexOf(b) : hierarchy.length),
  );
  return (
    <Panel
      title="Provider & reference evidence"
      meta={
        historical
          ? "HISTORICAL · no current freshness claim"
          : "Backend source evidence at emission"
      }
    >
      <p className="muted panelNote">
        A connected WebSocket does not establish healthy prices or quote
        authorization. Source freshness is reported at emission; displayed ages
        advance locally without renewing timestamps. Provider freshness budgets
        are unavailable in this contract. Yahoo observations are separate,
        research-only evidence and carry no price authority.
      </p>
      {!evidence.length ? (
        <Empty>
          Provider evidence unavailable. Configuration or enabled status cannot
          be inferred.
        </Empty>
      ) : (
        <div
          className="tableWrap providerTable"
          role="region"
          aria-label="Reported provider evidence"
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th scope="col">Provider / role</th>
                <th scope="col">Reported price</th>
                <th scope="col">Source / observation time</th>
                <th scope="col">Age / freshness</th>
                <th scope="col">Transport / status</th>
              </tr>
            </thead>
            <tbody>
              {evidence.map(([key, e]) => (
                <tr key={key}>
                  <td>
                    <strong>{e.provider}</strong>
                    <small>
                      {roles[key] ?? "Role unavailable · no authority inferred"}
                    </small>
                    {e.simulated && <Badge tone="blue">SIMULATED</Badge>}
                  </td>
                  <td className="mono">{accountingValue(e.price)}</td>
                  <td>
                    <div>
                      Source:{" "}
                      {e.source_timestamp === null
                        ? "Null (not reported)"
                        : evidenceTime(e.source_timestamp)}
                    </div>
                    <small>Observed: {evidenceTime(e.observed_at)}</small>
                  </td>
                  <td>
                    <div>
                      {(e.age_ms / 1000).toFixed(1)}s ·{" "}
                      {e.source_timestamp ? "source age" : "observation age"}
                    </div>
                    <Badge
                      tone={
                        historical || !e.healthy || e.stale ? "warn" : "good"
                      }
                    >
                      {historical
                        ? "HISTORICAL"
                        : e.stale
                          ? "REPORTED STALE"
                          : e.healthy
                            ? "REPORTED FRESH AT EMISSION"
                            : "REPORTED UNAVAILABLE"}
                    </Badge>
                  </td>
                  <td>
                    {e.transport ?? "Unavailable"} /{" "}
                    {e.transport_quality ?? "Unavailable"}
                    <small>Reported status: {e.status}</small>
                    <small>
                      Reported error:{" "}
                      {e.error === null ? "Null (none reported)" : e.error}
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <details className="researchInset">
        <summary>Inspect consensus and source support</summary>
        <p>
          Reported consensus:{" "}
          {t.reference_consensus?.confidence_state ?? "Unavailable"} ·{" "}
          {historical ? "HISTORICAL" : "AT EMISSION"}
        </p>
        <p>
          Eligible providers:{" "}
          {t.reference_consensus?.eligible_providers.join(", ") ||
            "None reported"}
        </p>
        <ul>
          {t.reference_consensus?.reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
        <p className="muted">
          Missing providers are not assumed configured. Provider roles do not
          grant permission to execute orders; research-only sources do not enter
          price authority.
        </p>
      </details>
    </Panel>
  );
}
