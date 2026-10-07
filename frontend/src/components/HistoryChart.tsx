import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  LineSeries,
  type ISeriesApi,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { HistoryPoint } from "../types";
import { finite } from "../utils/format";
export type HistoryLine = {
  key: keyof HistoryPoint;
  label: string;
  color: string;
};
export function HistoryChart({
  points,
  lines,
  height = 220,
}: {
  points: HistoryPoint[];
  lines: HistoryLine[];
  height?: number;
}) {
  const container = useRef<HTMLDivElement>(null),
    chart = useRef<IChartApi | null>(null),
    series = useRef<Map<string, ISeriesApi<"Line">>>(new Map()),
    setup = useRef(lines);
  useEffect(() => {
    if (!container.current) return;
    const c = createChart(container.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#0a1420" },
        textColor: "#8da3b8",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#132231" },
        horzLines: { color: "#132231" },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: true,
        borderColor: "#223246",
      },
      rightPriceScale: { borderColor: "#223246" },
    });
    chart.current = c;
    for (const line of setup.current)
      series.current.set(
        line.key,
        c.addSeries(LineSeries, {
          color: line.color,
          lineWidth: 2,
          title: line.label,
          priceLineVisible: false,
        }),
      );
    const ro = new ResizeObserver(() =>
      c.applyOptions({ width: container.current?.clientWidth ?? 300 }),
    );
    ro.observe(container.current);
    return () => {
      ro.disconnect();
      c.remove();
      chart.current = null;
      series.current.clear();
    };
  }, [height]);
  useEffect(() => {
    for (const line of lines) {
      const values = new Map<number, number | null>();
      for (const p of points) {
        const time = Math.floor(Date.parse(p.timestamp) / 1000),
          value = finite(p[line.key]);
        if (Number.isFinite(time)) values.set(time, value);
      }
      series.current
        .get(line.key)
        ?.setData(
          [...values]
            .sort((a, b) => a[0] - b[0])
            .map(([time, value]) =>
              value === null
                ? { time: time as UTCTimestamp }
                : { time: time as UTCTimestamp, value },
            ),
        );
    }
    chart.current?.timeScale().fitContent();
  }, [points, lines]);
  return (
    <div
      ref={container}
      className="historyChart"
      aria-label={
        lines.map((l) => l.label).join(", ") + " over backend observation time"
      }
    />
  );
}
