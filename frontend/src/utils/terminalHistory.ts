import type {
  HistoryPoint,
  HistoryRange,
  TerminalHistory,
  TerminalState,
} from "../types";
import { sessionCurrent, type EvidenceState } from "./researchEvidence";
import { finite } from "./format";
export type Observation = Pick<HistoryPoint, "sequence" | "timestamp"> &
  Partial<HistoryPoint>;
export type ChartHistory = {
  session: string;
  range: string;
  points: Observation[];
};

// Backend sequence is the observation identity; rendered seconds are only buckets.
export function boundedObservations(
  points: Observation[],
  limit: number,
): Observation[] {
  const sequences = new Map<number, Observation>();
  for (const point of points)
    if (!sequences.has(point.sequence)) sequences.set(point.sequence, point);
  const seconds = new Map<number, Observation>();
  for (const point of [...sequences.values()].sort(
    (a, b) => a.sequence - b.sequence,
  )) {
    const time = Math.floor(Date.parse(point.timestamp) / 1000);
    if (Number.isFinite(time)) seconds.set(time, point);
  }
  return [...seconds.values()]
    .sort((a, b) => a.sequence - b.sequence)
    .slice(-Math.max(1, Math.min(1000, limit)));
}
export function mergeHistory(
  state: ChartHistory,
  history: TerminalHistory,
  limit: number,
): ChartHistory {
  if (history.session_id !== state.session || history.range !== state.range)
    return state;
  const watermark = Math.max(-1, ...history.points.map((p) => p.sequence));
  return {
    ...state,
    points: boundedObservations(
      [
        ...state.points.filter((p) => p.sequence > watermark),
        ...history.points,
      ],
      limit,
    ),
  };
}
export function chartData(points: Observation[], key: keyof HistoryPoint) {
  return [...points]
    .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
    .map((p) => ({
      time: Math.floor(Date.parse(p.timestamp) / 1000),
      value: p[key],
    }));
}
export function needsFit(
  previous: string | null,
  key: string,
  hasPoints: boolean,
) {
  return hasPoints && previous !== key;
}

export const historyRanges: HistoryRange[] = [
  "session",
  "1m",
  "5m",
  "15m",
  "1h",
];
export function effectiveRange(
  preference: HistoryRange,
  available?: HistoryRange[],
): HistoryRange {
  return available && !available.includes(preference) ? "session" : preference;
}
export function checkedHistory(
  data: TerminalHistory,
  expected: TerminalState,
  current: EvidenceState,
  range: HistoryRange,
  limit: number,
) {
  if (
    !sessionCurrent(expected, current) ||
    data.session_id !== expected.session_id ||
    data.range !== range
  )
    throw new Error("History session/range changed during request");
  if (!Array.isArray(data.points) || data.points.length > limit)
    throw new Error("History exceeds the requested observation bound");
  return data;
}
export function observationCounts(
  points: HistoryPoint[],
  key: "risk_state" | "agent_regime",
) {
  const counts: Record<string, number> = {};
  for (const p of points)
    if (p[key]) counts[p[key]!] = (counts[p[key]!] ?? 0) + 1;
  return counts;
}
// Chart values alone use floating-point display coordinates, never economic arithmetic.
export function historySeries(
  points: Observation[],
  key: string,
  percent = false,
) {
  return boundedObservations(points, 1000)
    .map((p) => {
      return {
        time: Math.floor(Date.parse(p.timestamp) / 1000),
        value: chartCoordinate(p[key as keyof HistoryPoint], percent),
      };
    })
    .sort((a, b) => a.time - b.time);
}

export function chartCoordinate(value: unknown, percent = false) {
  if (typeof value !== "number" && typeof value !== "string") return null;
  const number = finite(value);
  const scaled = number === null ? NaN : number * (percent ? 100 : 1);
  return Number.isFinite(scaled) ? scaled : null;
}
