import { Empty } from "./TerminalPrimitives";
export function StateDistribution({
  counts,
  label,
}: {
  counts: Record<string, number>;
  label: string;
}) {
  const entries = Object.entries(counts),
    total = entries.reduce((n, [, count]) => n + count, 0);
  return (
    <div className="stateDistribution" aria-label={label}>
      <h3>{label}</h3>
      <p className="muted">
        Retained observation counts · share of sample count, not time-weighted
        duration
      </p>
      {!total ? (
        <Empty>No observations</Empty>
      ) : (
        entries.map(([state, count]) => (
          <div className="distributionRow" key={state}>
            <span>{state}</span>
            <meter
              min={0}
              max={total}
              value={count}
              aria-label={`${state} share of retained samples`}
            />
            <span>{count} observations</span>
          </div>
        ))
      )}
    </div>
  );
}
