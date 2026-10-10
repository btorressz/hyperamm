import { useState } from "react";
import type { CandidateEvaluation, OptimizationResult } from "../../types";
import { Panel, Metrics } from "../TerminalPrimitives";
import { researchMetric } from "../SimulationPanel";
import { accountingValue } from "../../utils/researchEvidence";
export function ParameterChanges({
  candidate,
}: {
  candidate: CandidateEvaluation;
}) {
  return (
    <details>
      <summary>
        Inspect parameters & full fingerprint · {candidate.label}
      </summary>
      <p className="muted">
        Reported updates only. Unreported baseline parameter values are
        unavailable.
      </p>
      {(["strategy_updates", "agent_updates"] as const).map((group) => (
        <div key={group}>
          <h3>{group}</h3>
          <dl className="researchDetails">
            {Object.entries(candidate[group]).map(([key, value]) => (
              <div key={key}>
                <dt>
                  <code>{key}</code>
                </dt>
                <dd>
                  <code>{JSON.stringify(value)}</code>
                </dd>
              </div>
            ))}
          </dl>
          {!Object.keys(candidate[group]).length && (
            <p className="muted">No reported updates</p>
          )}
        </div>
      ))}
      <p>
        Configuration fingerprint:{" "}
        <code>{candidate.configuration_fingerprint}</code>
      </p>
    </details>
  );
}
export function CandidateEvidence({
  candidate,
}: {
  candidate: CandidateEvaluation;
}) {
  return (
    <Panel title={candidate.label} meta="RESEARCH CONFIGURATION">
      <div className="researchCardBody">
        <Metrics
          items={[
            ["Training score", accountingValue(candidate.training_score)],
            ["Validation score", accountingValue(candidate.validation_score)],
            [
              "Training score Δ vs baseline",
              accountingValue(candidate.score_delta),
            ],
          ]}
        />
        <ParameterChanges candidate={candidate} />
        {(["training", "validation"] as const).map((phase) => (
          <div key={phase}>
            <h3>
              {phase === "training"
                ? "Training performance"
                : "Validation evaluation only"}
            </h3>
            <Metrics
              items={Object.entries(candidate[`${phase}_aggregate`]).map(
                ([key, value]) => [key, researchMetric(key, value)],
              )}
            />
            {!candidate[phase].length && (
              <p className="muted">{phase} evidence unavailable</p>
            )}
            <details>
              <summary>Inspect {phase} scenario evidence</summary>
              {candidate[phase].map((e) => (
                <div key={e.scenario}>
                  <h3>{e.scenario}</h3>
                  <Metrics
                    items={[
                      [
                        "Backend objective score",
                        accountingValue(e.score.final_score),
                      ],
                      [
                        "Session PnL",
                        researchMetric("session_pnl", e.metrics.session_pnl),
                      ],
                      [
                        "Return",
                        researchMetric("return_pct", e.metrics.return_pct),
                      ],
                      [
                        "Maximum drawdown",
                        researchMetric(
                          "max_drawdown_pct",
                          e.metrics.max_drawdown_pct,
                        ),
                      ],
                      [
                        "Maximum inventory utilization",
                        researchMetric(
                          "max_inventory_utilization",
                          e.metrics.max_inventory_utilization,
                        ),
                      ],
                    ]}
                  />
                  <details>
                    <summary>Score components & run identity</summary>
                    <Metrics
                      items={Object.entries(e.score).map(([key, value]) => [
                        key,
                        accountingValue(value),
                      ])}
                    />
                    <code>{e.run_fingerprint}</code>
                  </details>
                </div>
              ))}
            </details>
          </div>
        ))}
        <details>
          <summary>Reported baseline metric deltas</summary>
          <Metrics
            items={Object.entries(candidate.baseline_delta).map(
              ([key, value]) => [key, researchMetric(key, value)],
            )}
          />
        </details>
      </div>
    </Panel>
  );
}
export function CandidateComparison({
  result,
}: {
  result: OptimizationResult;
}) {
  const candidates = [result.baseline, ...result.ranked_candidates.slice(0, 5)],
    [left, setLeft] = useState(0),
    [right, setRight] = useState(candidates.length > 1 ? 1 : 0);
  return (
    <section aria-label="Optimization candidate comparison">
      <Panel
        title="Highest-ranked candidates under this objective"
        meta={`${result.engine_version} · ${result.simulated ? "SIMULATED" : "Research mode unavailable"}`}
      >
        <p className="muted panelNote">
          {result.requested_candidate_count} requested ·{" "}
          {result.candidate_count} valid · {result.rejected_candidates.length}{" "}
          rejected · {Math.min(5, result.ranked_candidates.length)} shown of{" "}
          {result.ranked_candidates.length} ranked candidates returned. Backend
          order is preserved; training defines ranking, validation is
          evaluation-only.
        </p>
        <div
          className="tableWrap"
          tabIndex={0}
          aria-label="Ranked research candidates"
        >
          <table>
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Training score</th>
                <th>Validation score</th>
                <th>Training Δ vs baseline</th>
                <th>Parameters</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c, i) => (
                <tr key={`${i}:${c.configuration_fingerprint}`}>
                  <td>{i === 0 ? "BASELINE" : `${i}. ${c.label}`}</td>
                  <td>{accountingValue(c.training_score)}</td>
                  <td>{accountingValue(c.validation_score)}</td>
                  <td>{accountingValue(c.score_delta)}</td>
                  <td>
                    <ParameterChanges candidate={c} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <details className="researchInset">
          <summary>Inspect optimization provenance & objective</summary>
          <p>Training scenarios: {result.training_scenarios.join(", ")}</p>
          <p>Validation scenarios: {result.validation_scenarios.join(", ")}</p>
          <Metrics
            items={Object.entries(result.objective).map(([key, value]) => [
              key,
              accountingValue(value),
            ])}
          />
          <p className="muted">
            Scores are backend objective values, not guaranteed returns.
            Configuration fingerprints identify research inputs; they do not
            prove exchange execution or durable storage.
          </p>
        </details>
      </Panel>
      <div className="researchFilters">
        {(
          [
            ["Compare left", left, setLeft],
            ["Compare right", right, setRight],
          ] as const
        ).map(([label, value, set]) => (
          <label key={label}>
            {label}
            <select
              aria-label={label}
              value={value}
              onChange={(e) => set(Number(e.target.value))}
            >
              {candidates.map((c, i) => (
                <option key={i} value={i}>
                  {i === 0 ? "BASELINE" : c.label}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <div className="grid twoColumns">
        <CandidateEvidence candidate={candidates[left]} />
        <CandidateEvidence candidate={candidates[right]} />
      </div>
      <Panel
        title="Rejected candidates"
        meta="Not successful research outcomes"
      >
        {!result.rejected_candidates.length ? (
          <p className="muted panelNote">No rejected candidates reported.</p>
        ) : (
          result.rejected_candidates.map((c, i) => (
            <details className="researchInset" key={i}>
              <summary>Inspect rejected candidate {i + 1}</summary>
              <dl className="researchDetails">
                {Object.entries(c).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>
                      <code>{JSON.stringify(value)}</code>
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          ))
        )}
      </Panel>
    </section>
  );
}
