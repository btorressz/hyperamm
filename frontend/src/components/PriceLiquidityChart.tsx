import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  LineSeries,
  type ISeriesApi,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { TerminalState, HistoryRange, HistoryPoint } from "../types";
import { useTerminalHistory } from "../hooks/useTerminalHistory";
import { useDisplayStore } from "../stores/display";
import { finite, timestamp } from "../utils/format";
import { Panel, Empty } from "./TerminalPrimitives";
const lines = [
  ["mid_price", "Mid", "#66aaff"],
  ["fair_value", "Fair value", "#b7c9f1"],
  ["strategy_reference_price", "Strategy ref", "#bd9cff"],
  ["mark_price", "Mark", "#efa957"],
  ["oracle_price", "HL Oracle", "#ebd47b"],
  ["consensus_price", "Consensus", "#6ccbcf"],
  ["best_bid", "Authorized BID", "#3bd49b"],
  ["best_ask", "Authorized ASK", "#f36d7b"],
] as const;
export function PriceLiquidityChart({ t }: { t: TerminalState }) {
  const defaultRange = useDisplayStore((s) => s.defaultRange),
    [range, setRange] = useState<HistoryRange>(defaultRange),
    [visible, setVisible] = useState<string[]>([
      "mid_price",
      "fair_value",
      "best_bid",
      "best_ask",
    ]);
  const history = useTerminalHistory(range),
    ref = useRef<HTMLDivElement>(null),
    chart = useRef<IChartApi | null>(null),
    series = useRef(new Map<string, ISeriesApi<"Line">>()),
    lastTimes = useRef(new Map<string, number>()),
    retained = useRef(
      new Map<string, Array<{ time: UTCTimestamp; value?: number }>>(),
    );
  useEffect(() => {
    if (history.data && !history.data.available_ranges.includes(range))
      setRange("session");
  }, [history.data, range]);
  useEffect(() => {
    if (!ref.current) return;
    const c = createChart(ref.current, {
      height: 285,
      layout: {
        background: { type: ColorType.Solid, color: "#0a1420" },
        textColor: "#8da3b8",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#132231" },
        horzLines: { color: "#132231" },
      },
      rightPriceScale: { borderColor: "#223246" },
      timeScale: {
        timeVisible: true,
        secondsVisible: true,
        borderColor: "#223246",
      },
    });
    chart.current = c;
    for (const [key, label, color] of lines)
      series.current.set(
        key,
        c.addSeries(LineSeries, {
          color,
          title: label,
          lineWidth: key === "mid_price" ? 2 : 1,
          priceLineVisible: false,
        }),
      );
    const ro = new ResizeObserver(() =>
      c.applyOptions({ width: ref.current?.clientWidth ?? 300 }),
    );
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      c.remove();
      chart.current = null;
      series.current.clear();
    };
  }, []);
  useEffect(() => {
    if (history.data?.session_id !== t.session_id) return;
    lastTimes.current.clear();
    for (const [key] of lines) {
      const values = new Map<number, number | null>();
      for (const p of history.data.points) {
        const time = Math.floor(Date.parse(p.timestamp) / 1000);
        if (Number.isFinite(time)) values.set(time, finite(p[key]));
      }
      const data = [...values]
        .sort((a, b) => a[0] - b[0])
        .map(([time, value]) =>
          value === null
            ? { time: time as UTCTimestamp }
            : { time: time as UTCTimestamp, value },
        );
      retained.current.set(key, data);
      series.current.get(key)?.setData(data);
      if (data.length) lastTimes.current.set(key, Number(data.at(-1)!.time));
    }
    chart.current?.timeScale().fitContent();
  }, [history.data, t.session_id]);
  useEffect(() => {
    for (const [key] of lines)
      series.current.get(key)?.applyOptions({ visible: visible.includes(key) });
  }, [visible]);
  useEffect(() => {
    const time = Math.floor(Date.parse(t.emitted_at) / 1000);
    if (!Number.isFinite(time)) return;
    const auth = t.risk_authorization.authorized ? t.authorized_quotes : [],
      bids = auth.filter((q) => q.side === "BID"),
      asks = auth.filter((q) => q.side === "ASK");
    const point: Partial<HistoryPoint> = {
      mid_price: t.market.stale ? null : t.market.mid_price,
      fair_value: t.market.stale ? null : t.fair_value,
      strategy_reference_price: t.perp_context?.stale
        ? null
        : t.perp_context?.strategy_reference_price,
      mark_price: t.perp_context?.stale ? null : t.perp_context?.mark_price,
      oracle_price: t.perp_context?.stale ? null : t.perp_context?.oracle_price,
      consensus_price: t.reference_consensus?.consensus_price,
      best_bid: bids.length
        ? Math.max(...bids.map((q) => Number(q.price)))
        : null,
      best_ask: asks.length
        ? Math.min(...asks.map((q) => Number(q.price)))
        : null,
    };
    for (const [key] of lines) {
      if (time < (lastTimes.current.get(key) ?? 0)) continue;
      const value = finite(point[key]);
      series.current
        .get(key)
        ?.update(
          value === null
            ? { time: time as UTCTimestamp }
            : { time: time as UTCTimestamp, value },
        );
      const data = retained.current.get(key) ?? [];
      const next =
        value === null
          ? { time: time as UTCTimestamp }
          : { time: time as UTCTimestamp, value };
      if (data.at(-1)?.time === time) data[data.length - 1] = next;
      else data.push(next);
      if (data.length > 1000) {
        data.splice(0, data.length - 1000);
        series.current.get(key)?.setData(data);
      }
      retained.current.set(key, data);
      lastTimes.current.set(key, time);
    }
  }, [t]);
  return (
    <Panel
      title="Price & authorized liquidity"
      meta={`${t.market.mode} · ${timestamp(t.emitted_at)}`}
      className="chartPanel"
    >
      <div className="chartToolbar">
        <div className="segmented">
          {(["1m", "5m", "15m", "1h", "session"] as HistoryRange[]).map((r) => (
            <button
              key={r}
              disabled={!history.data?.available_ranges.includes(r)}
              aria-pressed={range === r}
              onClick={() => setRange(r)}
            >
              {r === "session" ? "Session" : r}
            </button>
          ))}
        </div>
        <span className="muted">
          Current session · {history.data?.retained_points ?? "—"} observations
        </span>
      </div>
      <div ref={ref} />
      <div className="chartLegend">
        {lines.map(([key, label, color]) => (
          <label key={key}>
            <input
              type="checkbox"
              checked={visible.includes(key)}
              onChange={() =>
                setVisible((v) =>
                  v.includes(key) ? v.filter((x) => x !== key) : [...v, key],
                )
              }
            />
            <span style={{ color }}>{label}</span>
          </label>
        ))}
      </div>
      {history.isPending && <Empty>Loading bounded backend history…</Empty>}
      {history.isError && (
        <p className="inlineError" role="alert">
          History unavailable: {String(history.error)}
        </p>
      )}
    </Panel>
  );
}
