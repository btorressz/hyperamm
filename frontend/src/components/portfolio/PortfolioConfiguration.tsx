import type { FormDraft, Preview } from "../../types/portfolioResearch";
import {
  markets,
  riskLabels,
  decimalDisplay,
} from "../../utils/portfolioResearch";
import { Panel, Metrics } from "../TerminalPrimitives";
export type Edit = (update: (d: FormDraft) => FormDraft) => void;
export function Field({
  label,
  value,
  onChange,
  integer = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (s: string) => void;
  integer?: boolean;
  disabled?: boolean;
}) {
  return (
    <label>
      {label}
      <input
        inputMode={integer ? "numeric" : "decimal"}
        maxLength={80}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
    </label>
  );
}
export function PortfolioConfiguration({
  d,
  edit,
  preview,
  scenarios,
}: {
  d: FormDraft;
  edit: Edit;
  preview: Preview | null;
  scenarios: { name: string; description: string }[];
}) {
  return (
    <div className="stack">
      <Panel title="Capital Allocation" meta="EXACT USDC · LOCAL DRAFT">
        <div className="formGrid">
          <Field
            label="Total hypothetical capital (USDC)"
            value={d.budget.total_equity_quote}
            onChange={(v) =>
              edit((x) => ({
                ...x,
                budget: { ...x.budget, total_equity_quote: v },
              }))
            }
          />
          <Field
            label="Minimum reserve (USDC)"
            value={d.budget.minimum_reserve_quote}
            onChange={(v) =>
              edit((x) => ({
                ...x,
                budget: { ...x.budget, minimum_reserve_quote: v },
              }))
            }
          />
        </div>
        <p className="muted">
          Illustrative amounts are hypothetical, not a trading recommendation.
          Select one, two or three markets.
        </p>
        <div className="portfolioAllocations">
          {markets.map((m) => {
            const allocation = d.allocations.find((a) => a.market === m);
            return (
              <div className="portfolioAllocation" key={m}>
                <label className="portfolioToggle">
                  <input
                    type="checkbox"
                    checked={!!allocation}
                    onChange={(e) =>
                      edit((x) => ({
                        ...x,
                        allocations: e.target.checked
                          ? [
                              ...x.allocations,
                              { market: m, allocated_equity_quote: "10000" },
                            ]
                          : x.allocations.filter((a) => a.market !== m),
                      }))
                    }
                  />
                  {m}-PERP
                </label>
                <Field
                  label={`${m} allocation (USDC)`}
                  value={allocation?.allocated_equity_quote ?? ""}
                  disabled={!allocation}
                  onChange={(v) =>
                    edit((x) => ({
                      ...x,
                      allocations: x.allocations.map((a) =>
                        a.market === m
                          ? { ...a, allocated_equity_quote: v }
                          : a,
                      ),
                    }))
                  }
                />
                <span>
                  {preview?.allocation_percentages[m] !== undefined
                    ? preview.allocation_percentages[m] + "%"
                    : "Percentage requires preview"}
                </span>
              </div>
            );
          })}
        </div>
        <Metrics
          items={[
            [
              "Validated allocated capital",
              decimalDisplay(preview?.allocated_quote, "USDC"),
            ],
            [
              "Validated remaining reserve",
              decimalDisplay(preview?.reserve_quote, "USDC"),
            ],
          ]}
        />
      </Panel>
      <Panel
        title="Strategy & Scenario Configuration"
        meta="ISOLATED NATIVE PAPER ENGINE"
      >
        <p>
          Native adaptive AMM market making. Size and liquidity inputs use the
          existing ETH reference template; Python prepares the selected market
          profiles and captures the exact settings.
        </p>
        <div className="formGrid">
          <label>
            Baseline PAPER scenario
            <select
              aria-label="Baseline PAPER scenario"
              value={d.scenario}
              onChange={(e) =>
                edit((x) => ({ ...x, scenario: e.target.value }))
              }
            >
              {scenarios.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <Field
            label="Frames per market"
            integer
            value={d.frames}
            onChange={(v) => edit((x) => ({ ...x, frames: v }))}
          />
          <label>
            AMM model
            <select
              aria-label="AMM model"
              value={d.strategy.amm_model}
              onChange={(e) =>
                edit((x) => ({
                  ...x,
                  strategy: {
                    ...x.strategy,
                    amm_model: e.target
                      .value as FormDraft["strategy"]["amm_model"],
                  },
                }))
              }
            >
              <option value="CONSTANT_PRODUCT">Constant product</option>
              <option value="CONCENTRATED">Concentrated</option>
            </select>
          </label>
          {(
            [
              "levels_per_side",
              "max_distance_bps",
              "base_order_size",
              "total_liquidity",
              "concentration_factor",
            ] as const
          ).map((k) => (
            <Field
              key={k}
              label={
                {
                  levels_per_side: "Quote levels per side",
                  max_distance_bps: "Maximum distance (bps)",
                  base_order_size: "Base order size (ETH template)",
                  total_liquidity: "Liquidity per side (ETH template)",
                  concentration_factor: "Concentration factor",
                }[k]
              }
              value={d.strategy[k]}
              integer={k === "levels_per_side"}
              onChange={(v) =>
                edit((x) => ({ ...x, strategy: { ...x.strategy, [k]: v } }))
              }
            />
          ))}
          {(
            ["inventory_skew_enabled", "market_adaptation_enabled"] as const
          ).map((k) => (
            <label className="portfolioToggle" key={k}>
              <input
                type="checkbox"
                checked={d.strategy[k]}
                onChange={(e) =>
                  edit((x) => ({
                    ...x,
                    strategy: { ...x.strategy, [k]: e.target.checked },
                  }))
                }
              />
              {k === "inventory_skew_enabled"
                ? "Inventory skew strategy"
                : "Market adaptation strategy"}
            </label>
          ))}
        </div>
        <details>
          <summary>PAPER execution and accounting assumptions</summary>
          <div className="formGrid">
            <label>
              Fill model
              <select
                aria-label="Fill model"
                value={d.paper.execution.mode}
                onChange={(e) =>
                  edit((x) => ({
                    ...x,
                    paper: {
                      ...x.paper,
                      execution:
                        e.target.value === "BASELINE"
                          ? {
                              mode: "BASELINE",
                              order_latency_ms: "0",
                              cancel_latency_ms: "0",
                              slippage_bps: "0",
                              depth_sensitive: false,
                              allow_partial_fills: true,
                              participation_rate: "1",
                              max_fill_fraction: "1",
                            }
                          : { ...x.paper.execution, mode: "MODELED_CROSSING" },
                    },
                  }))
                }
              >
                <option value="BASELINE">Baseline crossing only</option>
                <option value="MODELED_CROSSING">
                  Modeled crossing sensitivity
                </option>
              </select>
            </label>
            <label className="portfolioToggle">
              <input
                type="checkbox"
                checked={d.paper.fee_enabled}
                onChange={(e) =>
                  edit((x) => ({
                    ...x,
                    paper: { ...x.paper, fee_enabled: e.target.checked },
                  }))
                }
              />
              Simulated fees enabled
            </label>
            <Field
              label="Maker fee (bps)"
              value={d.paper.maker_fee_bps}
              onChange={(v) =>
                edit((x) => ({ ...x, paper: { ...x.paper, maker_fee_bps: v } }))
              }
            />
            <Field
              label="Taker fee (bps)"
              value={d.paper.taker_fee_bps}
              onChange={(v) =>
                edit((x) => ({ ...x, paper: { ...x.paper, taker_fee_bps: v } }))
              }
            />
            <label className="portfolioToggle">
              <input
                type="checkbox"
                checked={d.paper.funding_enabled}
                onChange={(e) =>
                  edit((x) => ({
                    ...x,
                    paper: { ...x.paper, funding_enabled: e.target.checked },
                  }))
                }
              />
              Simulated funding enabled
            </label>
            <label>
              Funding accrual interval
              <select
                aria-label="Funding accrual interval"
                value={d.paper.funding_interval_seconds}
                onChange={(e) =>
                  edit((x) => ({
                    ...x,
                    paper: {
                      ...x.paper,
                      funding_interval_seconds: Number(e.target.value),
                    },
                  }))
                }
              >
                {[1, 60, 300, 3600, 28800, 86400].map((i) => (
                  <option key={i} value={i}>
                    {i} seconds
                  </option>
                ))}
              </select>
            </label>
            {d.paper.execution.mode === "MODELED_CROSSING" && (
              <>
                {(
                  [
                    "order_latency_ms",
                    "cancel_latency_ms",
                    "slippage_bps",
                    "participation_rate",
                    "max_fill_fraction",
                  ] as const
                ).map((k) => (
                  <Field
                    key={k}
                    label={
                      {
                        order_latency_ms: "Order latency (ms)",
                        cancel_latency_ms: "Cancel latency (ms)",
                        slippage_bps: "Slippage (bps)",
                        participation_rate: "Participation fraction",
                        max_fill_fraction: "Maximum fill fraction",
                      }[k]
                    }
                    value={d.paper.execution[k]}
                    onChange={(v) =>
                      edit((x) => ({
                        ...x,
                        paper: {
                          ...x.paper,
                          execution: { ...x.paper.execution, [k]: v },
                        },
                      }))
                    }
                  />
                ))}
                {(["depth_sensitive", "allow_partial_fills"] as const).map(
                  (k) => (
                    <label className="portfolioToggle" key={k}>
                      <input
                        type="checkbox"
                        checked={d.paper.execution[k]}
                        onChange={(e) =>
                          edit((x) => ({
                            ...x,
                            paper: {
                              ...x.paper,
                              execution: {
                                ...x.paper.execution,
                                [k]: e.target.checked,
                              },
                            },
                          }))
                        }
                      />
                      {k === "depth_sensitive"
                        ? "Depth sensitive"
                        : "Allow partial fills"}
                    </label>
                  ),
                )}
              </>
            )}
          </div>
          <p>
            Crossing-only PAPER fills. These assumptions are not venue queue
            evidence, predicted income or guaranteed passive fills.
          </p>
        </details>
      </Panel>
      <Panel
        title="Portfolio Risk Controls"
        meta="POST-EXECUTION RESEARCH LIMITS"
      >
        <div className="formGrid">
          {(Object.keys(riskLabels) as (keyof typeof riskLabels)[]).map((k) => (
            <Field
              key={k}
              label={riskLabels[k]}
              value={d.risk_limits[k]}
              onChange={(v) =>
                edit((x) => ({
                  ...x,
                  risk_limits: { ...x.risk_limits, [k]: v },
                }))
              }
            />
          ))}
          <Field
            label="Warning threshold ratio"
            value={d.risk_policy.warning_ratio}
            onChange={(v) =>
              edit((x) => ({
                ...x,
                risk_policy: { ...x.risk_policy, warning_ratio: v },
              }))
            }
          />
          <Field
            label="Reduction threshold ratio"
            value={d.risk_policy.reduction_ratio}
            onChange={(v) =>
              edit((x) => ({
                ...x,
                risk_policy: { ...x.risk_policy, reduction_ratio: v },
              }))
            }
          />
        </div>
        <p>
          Fractions use 0–1. Warning must be below reduction. Net exposure
          cannot exceed the gross ceiling. Validation is authoritative on the
          server.
        </p>
      </Panel>
    </div>
  );
}
