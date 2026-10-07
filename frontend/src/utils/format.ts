export function finite(x: unknown): number | null {
  if (x === null || x === undefined || x === "") return null;
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}
export function number(x: unknown, d = 2): string {
  const n = finite(x);
  return n === null
    ? "—"
    : n.toLocaleString(undefined, {
        maximumFractionDigits: d,
        minimumFractionDigits: Math.min(d, 2),
      });
}
export const price = (x: unknown) => number(x, 2);
export const quantity = (x: unknown) => number(x, 4);
export const money = (x: unknown) =>
  finite(x) === null ? "Unavailable" : `$${number(x, 2)}`;
export const percentage = (x: unknown, d = 1) =>
  finite(x) === null ? "—" : `${number(Number(x) * 100, d)}%`;
export const bps = (x: unknown) =>
  finite(x) === null ? "—" : `${number(x, 2)} bps`;
export const timestamp = (x: unknown) =>
  typeof x === "string" && Number.isFinite(Date.parse(x))
    ? new Date(x).toLocaleTimeString()
    : "—";
export const fingerprint = (x: unknown) =>
  typeof x === "string" && x ? `${x.slice(0, 12)}…` : "—";
