import type { TerminalState } from "../types";
import { Panel } from "./TerminalPrimitives";
import { Badge } from "./Badge";
export function SystemHealth({
  t,
  compact = false,
}: {
  t: TerminalState;
  compact?: boolean;
}) {
  const states = Object.entries(t.system_health.subsystems);
  return (
    <Panel
      title="System health"
      meta={`${t.system_health.status} · OBSERVATIONAL`}
    >
      <div className="healthGrid">
        {(compact
          ? states.filter(([k]) =>
              [
                "market_feed",
                "reference_consensus",
                "risk",
                "accounting",
                "execution_accounting_consistency",
              ].includes(k),
            )
          : states
        ).map(([name, state]) => (
          <div key={name}>
            <span>{name === "risk" ? "last risk decision" : name === "final_authorization" ? "last authorization" : name.replaceAll("_", " ")}</span>
            <Badge
              tone={
                state.status === "HEALTHY"
                  ? "good"
                  : state.status === "HALTED"
                    ? "bad"
                    : "warn"
              }
            >
              {state.status}
            </Badge>
            <small>{state.reason}</small>
          </div>
        ))}
      </div>
    </Panel>
  );
}
