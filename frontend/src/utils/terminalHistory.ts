import type { HistoryPoint, TerminalHistory } from "../types";
export type Observation = Pick<HistoryPoint, "sequence" | "timestamp"> & Partial<HistoryPoint>;
export type ChartHistory = { session: string; range: string; points: Observation[] };

// Backend sequence is the observation identity; rendered seconds are only buckets.
export function boundedObservations(points: Observation[], limit: number): Observation[] {
  const sequences = new Map<number, Observation>();
  for (const point of points) if (!sequences.has(point.sequence)) sequences.set(point.sequence, point);
  const seconds = new Map<number, Observation>();
  for (const point of [...sequences.values()].sort((a, b) => a.sequence - b.sequence)) {
    const time = Math.floor(Date.parse(point.timestamp) / 1000);
    if (Number.isFinite(time)) seconds.set(time, point);
  }
  return [...seconds.values()].sort((a, b) => a.sequence - b.sequence)
    .slice(-Math.max(1, Math.min(1000, limit)));
}
export function mergeHistory(state: ChartHistory, history: TerminalHistory, limit: number): ChartHistory {
  if (history.session_id !== state.session || history.range !== state.range) return state;
  const watermark = Math.max(-1, ...history.points.map(p => p.sequence));
  return { ...state, points: boundedObservations([
    ...state.points.filter(p => p.sequence > watermark), ...history.points,
  ], limit) };
}
export function chartData(points: Observation[], key: keyof HistoryPoint) {
  return [...points].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
    .map(p => ({ time: Math.floor(Date.parse(p.timestamp) / 1000), value: p[key] }));
}
export function needsFit(previous: string | null, key: string, hasPoints: boolean) {
  return hasPoints && previous !== key;
}
