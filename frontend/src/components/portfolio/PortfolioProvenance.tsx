import { useState } from "react";
import type { Preview, TerminalResult } from "../../types/portfolioResearch";
import { Panel, Empty } from "../TerminalPrimitives";
function Identifier({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  const [notice, setNotice] = useState("");
  return (
    <div className="portfolioIdentifier">
      <span>{label}</span>
      <code>{value ?? "Unavailable"}</code>
      {value && (
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard
              ?.writeText(value)
              .then(() => setNotice("Copied"))
              .catch(() => setNotice("Copy unavailable"));
          }}
        >
          Copy {label}
        </button>
      )}
      <small role="status">{notice}</small>
    </div>
  );
}
export function PortfolioProvenance({
  preview,
  result,
}: {
  preview: Preview | null;
  result: TerminalResult | null;
}) {
  return (
    <Panel
      title="Provenance & Diagnostics"
      meta="SAME-JOB IDENTITIES · NO ATTESTATION"
    >
      <p>
        HYPOTHETICAL · PAPER ONLY · RESEARCH / READ ONLY · NOT EMPIRICAL
        CORRELATION · HISTORICAL SYNCHRONIZATION UNVERIFIED
      </p>
      <p>
        Fingerprints identify canonical inputs and same-job evidence. They are
        not cryptographic signatures or exchange-authenticated attestations.
      </p>
      {!preview ? (
        <Empty>
          Validate a draft to inspect server-generated configuration identities.
        </Empty>
      ) : (
        <details open>
          <summary>
            Validated portfolio configuration and captured assumptions
          </summary>
          <p>
            Portfolio configuration version: {preview.config.contract_version}
          </p>
          <Identifier
            label="Configuration fingerprint"
            value={preview.config_fingerprint}
          />
          {preview.config.scenarios.map((s) => (
            <details key={s.market}>
              <summary>
                {s.market}-PERP · {s.scenario} · {s.frames} frames
              </summary>
              <Identifier
                label={`${s.market} market-profile fingerprint`}
                value={s.captured.market_profile_fingerprint}
              />
              <Identifier
                label={`${s.market} captured configuration fingerprint`}
                value={s.captured.fingerprint}
              />
              <pre>
                {JSON.stringify(JSON.parse(s.captured.canonical_json), null, 2)}
              </pre>
            </details>
          ))}
          {preview.stress && (
            <>
              <h3>Modeled shock assumptions</h3>
              <pre>{JSON.stringify(preview.stress, null, 2)}</pre>
            </>
          )}
        </details>
      )}
      {result && (
        <details open>
          <summary>Accepted research evidence</summary>
          <Identifier
            label="Terminal projection fingerprint"
            value={result.evidence_fingerprint}
          />
          <Identifier
            label="Original result fingerprint"
            value={result.source_result_fingerprint}
          />
          <Identifier
            label="Request fingerprint"
            value={result.request_fingerprint}
          />
          <Identifier
            label="Stress scenario fingerprint"
            value={result.scenario_fingerprint}
          />
          {[result.baseline, ...(result.stressed ? [result.stressed] : [])].map(
            (leg, i) => (
              <details key={i}>
                <summary>
                  {i ? "Stressed" : "Baseline"} · {leg.temporal.classification}
                </summary>
                <Identifier
                  label="Original analysis fingerprint"
                  value={leg.analysis_fingerprint}
                />
                <Identifier
                  label="Original bundle fingerprint"
                  value={leg.bundle_fingerprint}
                />
                <Identifier
                  label="Accounting fingerprint"
                  value={leg.accounting.evidence_fingerprint}
                />
                <Identifier
                  label="Chart source equity fingerprint"
                  value={leg.charts.equity_series_fingerprint}
                />
                <Identifier
                  label="Chart projection fingerprint"
                  value={leg.charts.evidence_fingerprint}
                />
                {leg.markets.map((m) => (
                  <details key={m.market}>
                    <summary>{m.market}-PERP source identities</summary>
                    {(
                      [
                        "market_profile_fingerprint",
                        "dataset_fingerprint",
                        "run_fingerprint",
                        "result_fingerprint",
                        "accounting_fingerprint",
                        "receipt_fingerprint",
                      ] as const
                    ).map((k) => (
                      <Identifier
                        key={k}
                        label={`${m.market} ${k.replaceAll("_", " ")}`}
                        value={m[k]}
                      />
                    ))}
                    <pre>
                      {JSON.stringify(m.execution_assumptions, null, 2)}
                    </pre>
                  </details>
                ))}
              </details>
            ),
          )}
          <ul>
            {result.limitations.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}
