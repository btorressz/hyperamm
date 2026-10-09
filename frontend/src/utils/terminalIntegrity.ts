// Localhost publisher cadence is ~1s; match the connection watchdog's 5s budget.
export const MAX_TERMINAL_ENVELOPE_AGE_MS = 5000;
export const MAX_FUTURE_CLOCK_SKEW_MS = 2000;
export const RETIRED_IDENTITY_CAPACITY = 64;
export const DIAGNOSTIC_COUNT_MAX = 65535;
export type RejectionReason = "schema" | "stale" | "future" | "replay" | "sequence" | "timeRegression";
export type TerminalAcceptanceResult =
  | { accepted: true; restarted: boolean }
  | { accepted: false; reason: RejectionReason };
export function envelopeAgeMs(emittedAt: string, nowMs: number): number {
  return nowMs - Date.parse(emittedAt);
}
export function boundedIncrement(n: number): number {
  return Math.min(n + 1, DIAGNOSTIC_COUNT_MAX);
}

// Date.parse truncates sub-millisecond fractions. Compare the full ISO fraction
// as well so process ordering cannot hide a regression in backend microseconds.
export function compareEmissionTimes(a: string, b: string): number {
  const parts = (value: string) => ({
    second: Date.parse(value.replace(/\.\d+(?=Z|[+-]\d{2}:\d{2}$)/, "")),
    fraction: /\.(\d+)(?:Z|[+-]\d{2}:\d{2})$/.exec(value)?.[1] ?? "",
  });
  const x = parts(a), y = parts(b);
  if (x.second !== y.second) return x.second < y.second ? -1 : 1;
  const width = Math.max(x.fraction.length, y.fraction.length);
  const xf = x.fraction.padEnd(width, "0"), yf = y.fraction.padEnd(width, "0");
  return xf === yf ? 0 : xf < yf ? -1 : 1;
}

export function terminalEnvelopeFailure(emittedAt: string, nowMs: number): "stale" | "future" | null {
  if (!Number.isFinite(envelopeAgeMs(emittedAt, nowMs))) return "stale";
  if (compareEmissionTimes(emittedAt, new Date(nowMs - MAX_TERMINAL_ENVELOPE_AGE_MS).toISOString()) < 0) return "stale";
  if (compareEmissionTimes(emittedAt, new Date(nowMs + MAX_FUTURE_CLOCK_SKEW_MS).toISOString()) > 0) return "future";
  return null;
}
