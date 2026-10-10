import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  LineSeries,
  BaselineSeries,
  type ISeriesApi,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import {
  historySeries,
  needsFit,
  boundedObservations,
  chartCoordinate,
  type Observation,
} from "../utils/terminalHistory";
import { accountingValue, evidenceTime } from "../utils/researchEvidence";
export type HistoryLine = {
  key: string;
  label: string;
  color: string;
  unit?: string;
  percent?: boolean;
  signed?: boolean;
};
export type ChartPoint = {
  sequence: number;
  timestamp: string;
  [key: string]: unknown;
};
type Series = ISeriesApi<"Line" | "Baseline">;
export type SeriesEntry = {
  series: Series;
  signature: string;
  segments: Series[];
};
// Reconcile configuration after mount; label, scale, kind and removed-series changes are material.
export function reconcileSeries(
  c: IChartApi,
  entries: Map<string, SeriesEntry>,
  lines: HistoryLine[],
) {
  const keys = new Set(lines.map((l) => l.key));
  for (const [key, entry] of entries)
    if (!keys.has(key)) {
      c.removeSeries(entry.series);
      entry.segments.forEach((s) => c.removeSeries(s));
      entries.delete(key);
    }
  for (const line of lines) {
    const signature = JSON.stringify(line),
      previous = entries.get(line.key);
    if (previous?.signature === signature) continue;
    if (previous) {
      c.removeSeries(previous.series);
      previous.segments.forEach((s) => c.removeSeries(s));
    }
    const s = addChartSeries(c, line);
    entries.set(line.key, { series: s, signature, segments: [] });
  }
}
function addChartSeries(c: IChartApi, line: HistoryLine) {
  const options = {
    title: line.label,
    priceLineVisible: false,
    pointMarkersVisible: true,
    priceFormat: {
      type: "custom" as const,
      minMove: 0.0001,
      formatter: (n: number) =>
        `${n.toLocaleString(undefined, { maximumFractionDigits: 4 })}${line.percent ? "%" : line.unit ? " " + line.unit : ""}`,
    },
  };
  const s: Series = line.signed
    ? c.addSeries(BaselineSeries, {
        ...options,
        baseValue: { type: "price", price: 0 },
        topLineColor: "#4cd4a1",
        bottomLineColor: "#f0788a",
        topFillColor1: "#4cd4a122",
        topFillColor2: "#4cd4a105",
        bottomFillColor1: "#f0788a05",
        bottomFillColor2: "#f0788a22",
      })
    : c.addSeries(LineSeries, { ...options, color: line.color, lineWidth: 2 });
  if (line.signed)
    s.createPriceLine({
      price: 0,
      color: "#819bbc",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: false,
      title: "Zero",
    });
  return s;
}

export function seriesCoordinates(
  points: ChartPoint[],
  line: HistoryLine,
  axis: "time" | "frame",
) {
  if (axis === "time")
    return historySeries(points as Observation[], line.key, line.percent);
  return points.map((p) => {
    return {
      time: p.sequence,
      value: chartCoordinate(p[line.key], line.percent),
    };
  });
}
export function contiguousSegments(
  data: Array<{ time: number; value: number | null }>,
) {
  const segments: Array<Array<{ time: number; value: number }>> = [];
  let current: Array<{ time: number; value: number }> = [];
  for (const p of data) {
    if (p.value === null) {
      if (current.length) segments.push(current);
      current = [];
    } else current.push({ time: p.time, value: p.value });
  }
  if (current.length) segments.push(current);
  return segments;
}
export function plotSegments(
  c: IChartApi,
  entry: SeriesEntry,
  line: HistoryLine,
  data: Array<{ time: number; value: number | null }>,
) {
  const groups = contiguousSegments(data),
    count = Math.max(0, groups.length - 1);
  while (entry.segments.length > count) c.removeSeries(entry.segments.pop()!);
  while (entry.segments.length < count)
    entry.segments.push(addChartSeries(c, line));
  // Whitespace alone is skipped by Lightweight Charts' line renderer. Separate
  // contiguous series prevent drawing a false connection across missing evidence.
  const first = new Map(groups[0]?.map((p) => [p.time, p.value]) ?? []);
  entry.series.applyOptions({ lastValueVisible: count === 0 });
  entry.series.setData(
    data.map((p) =>
      first.has(p.time)
        ? { time: p.time as UTCTimestamp, value: first.get(p.time)! }
        : { time: p.time as UTCTimestamp },
    ),
  );
  entry.segments.forEach((s, i) => {
    s.applyOptions({ lastValueVisible: i === count - 1 });
    s.setData(
      groups[i + 1].map((p) => ({
        time: p.time as UTCTimestamp,
        value: p.value,
      })),
    );
  });
}

export function HistoryChart({
  points,
  lines,
  height = 220,
  fitKey = "initial",
  axis = "time",
}: {
  points: ChartPoint[] | Observation[];
  lines: HistoryLine[];
  height?: number;
  fitKey?: string;
  axis?: "time" | "frame";
}) {
  const container = useRef<HTMLDivElement>(null),
    chart = useRef<IChartApi | null>(null),
    series = useRef(new Map<string, SeriesEntry>()),
    fitted = useRef<string | null>(null);
  const evidence = useRef({ points, lines }),
    [tooltip, setTooltip] = useState<{
      time: string;
      values: Array<[string, string]>;
    } | null>(null);
  evidence.current = { points, lines };
  useEffect(() => {
    if (!container.current) return;
    const c = createChart(container.current, {
      height,
      width: container.current.clientWidth,
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
        ...(axis === "frame"
          ? { tickMarkFormatter: (time: unknown) => `F${time}` }
          : {}),
      },
      rightPriceScale: { borderColor: "#223246" },
      ...(axis === "frame"
        ? {
            localization: { timeFormatter: (time: unknown) => `Frame ${time}` },
          }
        : {}),
    });
    chart.current = c;
    fitted.current = null;
    c.subscribeCrosshairMove((param) => {
      if (
        param.time === undefined ||
        !param.point ||
        param.point.x < 0 ||
        param.point.y < 0
      ) {
        setTooltip(null);
        return;
      }
      const displayed =
        axis === "frame"
          ? evidence.current.points
          : boundedObservations(evidence.current.points as Observation[], 1000);
      const p = [...displayed]
        .reverse()
        .find((p) =>
          axis === "frame"
            ? p.sequence === Number(param.time)
            : Math.floor(Date.parse(p.timestamp) / 1000) === Number(param.time),
        );
      if (!p) {
        setTooltip(null);
        return;
      }
      setTooltip({
        time:
          axis === "frame"
            ? `Frame ${p.sequence} · ${evidenceTime(p.timestamp)}`
            : evidenceTime(p.timestamp),
        values: evidence.current.lines.map((l) => [
          l.label,
          chartValue(p[l.key as keyof typeof p], l),
        ]),
      });
    });
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
  }, [height, axis]);
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    reconcileSeries(c, series.current, lines);
    let hasValues = false;
    for (const line of lines) {
      const data = seriesCoordinates(points as ChartPoint[], line, axis);
      hasValues ||= data.some((p) => p.value !== null);
      const entry = series.current.get(line.key);
      if (entry) plotSegments(c, entry, line, data);
    }
    if (needsFit(fitted.current, fitKey, hasValues)) {
      c.timeScale().fitContent();
      fitted.current = fitKey;
      setTooltip(null);
    }
  }, [points, lines, fitKey, height, axis]);
  return (
    <div className="researchChart">
      <div className="chartLegend">
        {lines.map((l) => (
          <span key={l.key}>
            <i style={{ background: l.signed ? "#4cd4a1" : l.color }} />
            {l.signed && (
              <i style={{ background: "#f0788a" }} title="Negative values" />
            )}
            {l.label} · {l.percent ? "%" : (l.unit ?? "value")}
          </span>
        ))}
        <button
          type="button"
          aria-label={`Reset ${lines.map((l) => l.label).join(", ")} chart view`}
          onClick={() => chart.current?.timeScale().fitContent()}
        >
          Reset view
        </button>
      </div>
      <div
        ref={container}
        className="historyChart"
        aria-label={
          lines.map((l) => l.label).join(", ") +
          (axis === "frame"
            ? " over simulated frame index"
            : " over backend observation time")
        }
      />
      <div className="chartReadout" aria-live="off">
        {tooltip ? (
          <>
            <time>{tooltip.time}</time>
            {tooltip.values.map(([label, value]) => (
              <span key={label}>
                {label}: <b>{value}</b>
              </span>
            ))}
          </>
        ) : (
          "Hover a point to inspect reported values. Drag to pan; scroll to zoom."
        )}
      </div>
      {!points.length && (
        <p className="emptyEvidence">
          No observations available for this view.
        </p>
      )}
      {!!points.length &&
        !lines.some((line) =>
          seriesCoordinates(points as ChartPoint[], line, axis).some(
            (p) => p.value !== null,
          ),
        ) && (
          <p className="emptyEvidence">
            Plotted values are unavailable in these observations. Missing
            evidence is not zero.
          </p>
        )}
      <details className="researchInset">
        <summary>Inspect chart observations</summary>
        <div
          className="tableWrap"
          tabIndex={0}
          aria-label="Chart observation data"
        >
          <table>
            <thead>
              <tr>
                <th>{axis === "frame" ? "Frame" : "Sequence"}</th>
                <th>Backend timestamp</th>
                {lines.map((l) => (
                  <th key={l.key}>{l.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {points.map((p, i) => (
                <tr key={`${p.sequence}:${i}`}>
                  <td>{p.sequence}</td>
                  <td>{p.timestamp}</td>
                  {lines.map((l) => (
                    <td key={l.key}>
                      {chartValue(p[l.key as keyof typeof p], l)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
export function chartValue(value: unknown, line: HistoryLine) {
  const v = accountingValue(value, !!line.percent);
  return v === "Unavailable" || line.percent
    ? v
    : `${v}${line.unit ? " " + line.unit : ""}`;
}
