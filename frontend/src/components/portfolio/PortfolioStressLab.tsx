import type { FormDraft, StressKind } from "../../types/portfolioResearch";
import { stressKinds } from "../../utils/portfolioResearch";
import { Panel, StatusBanner } from "../TerminalPrimitives";
import { Field, type Edit } from "./PortfolioConfiguration";
export function PortfolioStressLab({ d, edit }: { d: FormDraft; edit: Edit }) {
  const fields = d.stressFields;
  const field = (key: string, label: string) => (
    <Field
      key={key}
      label={label}
      value={fields[key]}
      onChange={(v) =>
        edit((x) => ({ ...x, stressFields: { ...x.stressFields, [key]: v } }))
      }
    />
  );
  return (
    <Panel title="Stress Lab" meta="SIX EXPLICIT MODELED SCENARIOS">
      <StatusBanner>
        NOT EMPIRICAL CORRELATION · Transmission multipliers are hypothetical
        assumptions. Baseline and stress run together within one shared workload
        budget.
      </StatusBanner>
      <label className="portfolioToggle">
        <input
          type="checkbox"
          checked={d.stressEnabled}
          onChange={(e) =>
            edit((x) => ({ ...x, stressEnabled: e.target.checked }))
          }
        />
        Prepare baseline versus stressed comparison
      </label>
      <fieldset disabled={!d.stressEnabled}>
        <legend>Modeled shock assumptions</legend>
        <div className="formGrid">
          <label>
            Stress scenario
            <select
              aria-label="Stress scenario"
              value={d.stressKind}
              onChange={(e) =>
                edit((x) => ({
                  ...x,
                  stressKind: e.target.value as StressKind,
                  recovery:
                    e.target.value === "ORACLE_DEGRADATION"
                      ? "STEP_WINDOW"
                      : x.recovery,
                }))
              }
            >
              {Object.entries(stressKinds).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <Field
            label="Shock onset (zero-based frame)"
            integer
            value={d.onset}
            onChange={(v) => edit((x) => ({ ...x, onset: v }))}
          />
          <Field
            label="Shock duration (frames)"
            integer
            value={d.duration}
            onChange={(v) => edit((x) => ({ ...x, duration: v }))}
          />
          <label>
            Recovery profile
            <select
              aria-label="Recovery profile"
              value={d.recovery}
              onChange={(e) =>
                edit((x) => ({
                  ...x,
                  recovery: e.target.value as FormDraft["recovery"],
                }))
              }
            >
              <option value="STEP_WINDOW">Step window</option>
              <option
                value="LINEAR_TO_BASELINE"
                disabled={d.stressKind === "ORACLE_DEGRADATION"}
              >
                Linear to baseline
              </option>
            </select>
          </label>
          {d.stressKind === "CORRELATED_SELLOFF" &&
            d.allocations.map((a) => (
              <Field
                key={a.market}
                label={`${a.market} decline fraction (0–0.8)`}
                value={d.declines[a.market]}
                onChange={(v) =>
                  edit((x) => ({
                    ...x,
                    declines: { ...x.declines, [a.market]: v },
                  }))
                }
              />
            ))}
          {d.stressKind === "BTC_LED_VOLATILITY" && (
            <>
              {field("btc_decline_fraction", "BTC decline fraction (0–0.8)")}
              {d.allocations
                .filter((a) => a.market !== "BTC")
                .map((a) =>
                  field(
                    a.market.toLowerCase() + "_transmission",
                    `${a.market} modeled transmission multiplier (0–5)`,
                  ),
                )}
              {field("propagation_lag_frames", "Propagation lag (frames)")}
            </>
          )}
          {d.stressKind === "LIQUIDITY_SHOCK" && (
            <>
              {field("bid_depth_multiplier", "Bid depth multiplier (0–1)")}
              {field("ask_depth_multiplier", "Ask depth multiplier (0–1)")}
              {field("spread_multiplier", "Spread multiplier (1–20)")}
            </>
          )}
          {d.stressKind === "FUNDING_STRESS" &&
            d.allocations.map((a) => (
              <Field
                key={a.market}
                label={`${a.market} signed funding adjustment (−0.01–0.01)`}
                value={d.funding[a.market]}
                onChange={(v) =>
                  edit((x) => ({
                    ...x,
                    funding: { ...x.funding, [a.market]: v },
                  }))
                }
              />
            ))}
          {d.stressKind === "ORACLE_DEGRADATION" && (
            <>
              <label>
                Reference source
                <select
                  aria-label="Reference source"
                  value={fields.reference_source}
                  onChange={(e) =>
                    edit((x) => ({
                      ...x,
                      stressFields: {
                        ...x.stressFields,
                        reference_source: e.target.value,
                      },
                    }))
                  }
                >
                  {["redstone", "kraken", "coingecko"].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label>
                Reference degradation mode
                <select
                  aria-label="Reference degradation mode"
                  value={fields.reference_mode}
                  onChange={(e) =>
                    edit((x) => ({
                      ...x,
                      stressFields: {
                        ...x.stressFields,
                        reference_mode: e.target.value,
                      },
                    }))
                  }
                >
                  <option value="MISSING">Missing</option>
                  <option value="DIVERGENT">Divergent</option>
                </select>
              </label>
              {fields.reference_mode === "DIVERGENT" &&
                field(
                  "reference_divergence_fraction",
                  "Divergence fraction (0–0.5)",
                )}
            </>
          )}
          {d.stressKind === "CONCENTRATION_STRESS" &&
            field(
              "concentration_decline_fraction",
              "Adverse shock magnitude (0–0.8)",
            )}
        </div>
      </fieldset>
      {d.stressKind === "FUNDING_STRESS" && (
        <p>
          Enable funding accounting and select an accrual interval observed
          within the shock window. Signed adjustments must be nonzero; no
          projected venue funding is implied.
        </p>
      )}
      {d.stressKind === "ORACLE_DEGRADATION" && (
        <p>
          Stale oracle timestamps are not supported by the current model.
          Missing or divergent source evidence only; linear recovery is
          unavailable.
        </p>
      )}
      {d.stressKind === "CONCENTRATION_STRESS" && (
        <p>
          The backend selects the largest validated pre-onset position exposure,
          applies an adverse directional shock and verifies the unchanged replay
          prefix. Complete histories and a nonzero pre-onset position are
          required.
        </p>
      )}
      <p>
        Shock onset + propagation lag + duration must fit the captured frame
        window. Transmitted declines cannot exceed 0.8. Concentration requires
        onset after frame zero.
      </p>
    </Panel>
  );
}
