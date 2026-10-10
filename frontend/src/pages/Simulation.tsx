import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { OptimizationResult, SimulationResult } from "../types";
import { SimulationPanel } from "../components/SimulationPanel";
import { SimulationTrace } from "../components/simulation/SimulationTrace";
import { CandidateComparison } from "../components/simulation/CandidateComparison";
import { Panel, Empty, StatusBanner } from "../components/TerminalPrimitives";
import { Badge } from "../components/Badge";
import {
  optimizationPresets,
  frameError,
  presetCandidateCount,
  ResearchRunGate,
  trainingScenarios,
  validationScenarios,
  type RunConfiguration,
} from "../utils/simulationResearch";
import "../phase10.css";
import "../phase1331.css";
import "../phase1332.css";
export function Simulation() {
  const scenarios = useQuery({
    queryKey: ["simulation-scenarios"],
    queryFn: api.simulationScenarios,
  });
  const [scenario, setScenario] = useState("QUIET"),
    [frames, setFrames] = useState("120"),
    [preset, setPreset] =
      useState<keyof typeof optimizationPresets>("Balanced");
  const [result, setResult] = useState<{
      data: SimulationResult;
      config: RunConfiguration;
    } | null>(null),
    [opt, setOpt] = useState<{
      data: OptimizationResult;
      config: RunConfiguration;
      token: number;
    } | null>(null),
    [busy, setBusy] = useState<RunConfiguration | null>(null),
    [error, setError] = useState("");
  const gate = useRef(new ResearchRunGate());
  useEffect(() => () => gate.current.retire(), []);
  const selected = scenarios.data?.scenarios.find((s) => s.name === scenario),
    validation = frameError(frames);
  const catalogSupportsGrid = [
    ...trainingScenarios,
    ...validationScenarios,
  ].every((name) => scenarios.data?.scenarios.some((s) => s.name === name));
  const submit = async (kind: "run" | "opt") => {
    if (validation || !selected || (kind === "opt" && !catalogSupportsGrid))
      return;
    const token = gate.current.start();
    if (token === null) return;
    const config: RunConfiguration = {
      kind,
      scenario,
      frames: kind === "opt" ? Math.min(Number(frames), 250) : Number(frames),
      preset,
    };
    setBusy(config);
    setError("");
    try {
      if (kind === "run") {
        const data = await api.runSimulation({
          scenario: config.scenario,
          frames: config.frames,
          simulation: {
            max_frames: config.frames,
            record_trace: true,
            trace_max_points: 250,
          },
        });
        if (gate.current.current(token)) setResult({ data, config });
      } else {
        const { strategy_grid, agent_grid } =
          optimizationPresets[config.preset];
        const data = await api.optimizeSimulation({
          strategy_grid,
          agent_grid,
          training_scenarios: trainingScenarios,
          validation_scenarios: validationScenarios,
          frames: config.frames,
          max_candidates: 32,
          top_n: 5,
        });
        if (gate.current.current(token)) setOpt({ data, config, token });
      }
    } catch (e) {
      if (gate.current.current(token))
        setError(
          e instanceof TypeError
            ? "Network request failed. Check the local backend connection and retry. A lost browser request does not prove the research worker stopped."
            : e instanceof Error
              ? e.message
              : String(e),
        );
    } finally {
      if (gate.current.finish(token)) setBusy(null);
    }
  };
  return (
    <div className="researchWorkspace simulationPage stack">
      <div className="researchPageTitle">
        <div>
          <h1>Simulation & Optimization</h1>
          <p className="muted">
            Configure → run isolated PAPER research → inspect metrics → explore
            trace → compare outcomes
          </p>
        </div>
        <Badge tone="blue">SIMULATED · PAPER · OFFLINE</Badge>
      </div>
      <Panel
        title="Configure isolated research"
        meta="DETERMINISTIC CROSSING FILLS"
        className="simControls"
      >
        {scenarios.isPending && <Empty>Loading scenario catalog…</Empty>}
        {scenarios.isError && (
          <p className="inlineError" role="alert">
            Scenario catalog unavailable: {scenarios.error.message}{" "}
            <button type="button" onClick={() => void scenarios.refetch()}>
              Retry catalog
            </button>
          </p>
        )}
        <div className="formGrid">
          <label>
            Scenario
            <select
              aria-label="Scenario"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              disabled={!scenarios.data}
            >
              {(scenarios.data?.scenarios ?? []).map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Frames
            <input
              type="number"
              min={2}
              max={1000}
              step={1}
              value={frames}
              aria-invalid={!!validation}
              aria-describedby="frame-validation"
              onChange={(e) => setFrames(e.target.value)}
            />
          </label>
          <label>
            Optimization preset
            <select
              aria-label="Optimization preset"
              value={preset}
              onChange={(e) =>
                setPreset(e.target.value as keyof typeof optimizationPresets)
              }
            >
              {Object.keys(optimizationPresets).map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
        </div>
        <p
          id="frame-validation"
          className={validation ? "inlineError" : "muted panelNote"}
        >
          {validation ||
            "UI bound: 2–1000 whole frames. Grid search uses min(selected frames, 250) per scenario; server validation remains authoritative."}
        </p>
        <div className="grid twoColumns researchInset">
          <div>
            <h3>Scenario evidence</h3>
            <p>
              {selected?.description ?? "Choose a supported backend scenario."}
            </p>
            <p className="muted">
              Inspect simulated performance, fills, inventory, risk observations
              and up to 250 trace points. Research copies current backend
              strategy/agent/risk settings into isolated PAPER state.
            </p>
          </div>
          <div>
            <h3>{preset} parameter study</h3>
            <p>{optimizationPresets[preset].description}</p>
            <p className="muted">
              Strategy:{" "}
              {Object.keys(optimizationPresets[preset].strategy_grid).join(
                ", ",
              )}
              <br />
              Agents:{" "}
              {Object.keys(optimizationPresets[preset].agent_grid).join(", ") ||
                "No agent parameters varied"}
              <br />
              {presetCandidateCount(preset)} grid candidates · request cap 32 ·
              backend hard cap 128 · top 5
            </p>
            <p className="muted">
              Training: {trainingScenarios.join(", ")}
              <br />
              Validation: {validationScenarios.join(", ")}
            </p>
            {scenarios.data && !catalogSupportsGrid && (
              <p className="inlineError">
                Required preset scenarios are unavailable in the backend
                catalog.
              </p>
            )}
          </div>
        </div>
        <div className="actions">
          <button
            type="button"
            className="primary"
            disabled={!!busy || !!validation || !selected}
            onClick={() => void submit("run")}
          >
            {busy?.kind === "run" ? "Running…" : "Run Simulation"}
          </button>
          <button
            type="button"
            disabled={
              !!busy || !!validation || !selected || !catalogSupportsGrid
            }
            onClick={() => void submit("opt")}
          >
            {busy?.kind === "opt" ? "Optimizing…" : "Run Bounded Grid Search"}
          </button>
        </div>
        {busy && (
          <p role="status" className="muted panelNote">
            {busy.kind === "run"
              ? `Running ${busy.scenario}`
              : `Evaluating ${busy.preset} grid`}{" "}
            · {busy.frames} frames per scenario. Waiting for bounded backend
            research; no progress percentage is reported. Controls describe the
            next request; completed results keep their captured configuration.
          </p>
        )}
        {error && (
          <p className="inlineError" role="alert">
            {error}
          </p>
        )}
        <p className="muted panelNote">
          Research only. Results never modify the live strategy, risk settings,
          TESTNET state, or kill switch. One request at a time. Leaving this
          page does not prove the backend worker stopped.
        </p>
      </Panel>
      {!result && !opt && (
        <Empty>
          Run a scenario to inspect performance and trace evidence, or a bounded
          grid to compare candidates.
        </Empty>
      )}
      {result && (
        <section aria-label="Completed simulation" className="stack">
          <div className="researchPageTitle">
            <h2>Completed run · {result.data.scenario}</h2>
            <Badge tone="blue">
              {result.data.simulated
                ? "SIMULATED RESULT"
                : "Research mode unavailable"}{" "}
              · {result.config.frames} requested frames
            </Badge>
          </div>
          <p className="muted">
            Captured request: {result.config.scenario} · {result.config.frames}{" "}
            frames. Results remain associated with this request when controls
            change.
          </p>
          <SimulationPanel m={result.data.metrics} />
          <SimulationTrace result={result.data} />
          <Panel
            title="Simulation provenance & limitations"
            meta={result.data.engine_version}
          >
            <details className="researchInset">
              <summary>Inspect full research fingerprints</summary>
              <dl className="researchDetails">
                {(
                  [
                    "run_fingerprint",
                    "dataset_fingerprint",
                    "strategy_fingerprint",
                  ] as const
                ).map((key) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>
                      <code>{result.data[key]}</code>
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
            <ul className="researchReasons">
              {result.data.limitations.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </Panel>
        </section>
      )}
      {opt && (
        <section aria-label="Completed optimization" className="stack">
          <h2>Completed parameter study · {opt.config.preset}</h2>
          <p className="muted">
            Captured request: {opt.config.preset} · {opt.config.frames} frames
            per scenario · backend ranking preserved.
          </p>
          <CandidateComparison key={opt.token} result={opt.data} />
        </section>
      )}
      <StatusBanner>
        Deterministic crossing-only PAPER research does not establish real queue
        priority, hidden liquidity, actual network latency, stochastic fills,
        guaranteed execution quality or future profitability. Validation is
        evaluation-only. Fingerprints identify research; results are not a
        durable saved research vault.
      </StatusBanner>
    </div>
  );
}
