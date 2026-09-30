import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import ChartTooltip from "./ChartTooltip";
import { GRADE_COLORS } from "./chartTheme";
import type { QualityPoint } from "../api/types";

/**
 * Average score over time, with a shaded best-to-worst band behind the line.
 *
 * The band is the point. An average that climbs while one agent collapses reads
 * as progress on a plain line chart, and reads as trouble the moment the spread
 * is drawn behind it — so direction and dispersion are shown together rather
 * than one at a time.
 *
 * The band is decoration in the accessibility sense: every number it represents
 * is also in the tooltip as words — best, worst, average, agents — so nothing
 * here depends on seeing the shading.
 *
 * One point per scan. A gap between two scans is deliberately not filled: no
 * scan is no measurement, not a score of zero.
 */
export default function QualityTrend({
  points,
  height = 280,
}: {
  points: QualityPoint[];
  height?: number;
}) {
  if (points.length === 0) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        Nothing to plot for this selection yet.
      </p>
    );
  }

  const data = points.map((p) => ({
    ...p,
    // Recharts draws a band from a two-value datum; the low edge and the height
    // are kept separate so the tooltip can name both ends in words.
    band: [p.min_score, p.max_score] as [number, number],
  }));

  const label = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleDateString(undefined, {
          day: "numeric",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "";

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
          <XAxis
            dataKey="captured_at"
            tickFormatter={(v) =>
              new Date(String(v)).toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
              })
            }
            stroke="#94a3b8"
            fontSize={11}
            minTickGap={28}
          />
          <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 100]} allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} labelFormatter={(v) => label(String(v))} />
          <Area
            dataKey="band"
            name="Worst to best agent"
            stroke="none"
            fill={GRADE_COLORS.B}
            fillOpacity={0.18}
            activeDot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="avg_score"
            name="Average score"
            stroke="#3b6ef5"
            strokeWidth={2.5}
            dot={{ r: 2 }}
          />
          <Line
            type="monotone"
            dataKey="min_score"
            name="Worst agent"
            stroke="#94a3b8"
            strokeWidth={1}
            strokeDasharray="4 3"
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="max_score"
            name="Best agent"
            stroke="#94a3b8"
            strokeWidth={1}
            strokeDasharray="1 3"
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
