import {
  Bar,
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
 * Average score per **scan**, as bars with a trailing-average trend line.
 *
 * The suite's personal pages all carry this shape, and the visual treatment here
 * is deliberately the same as theirs — same bar-plus-line, same trend stroke,
 * same tooltip. What is **not** the same is the x-axis, and it is worth being
 * explicit about why this is a separate component rather than a mode on the
 * siblings' `ActivityTimeline`.
 *
 * There, a point is a calendar day, and a day with no prompts genuinely is a
 * zero — so filling the empty days is honest, and omitting them would compress
 * a fortnight of silence into one gridline.
 *
 * Here, a point is a scan. A day with no scan is not a score of zero; it is no
 * measurement. Filling it would draw a collapse that never happened. The two
 * behaviours are opposite, so a shared component would need a flag that changes
 * what the chart *claims*, which is the kind of flag nobody reads before using.
 */
export default function ScoreTimeline({
  points,
  trendWindow = 3,
  height = 220,
}: {
  points: QualityPoint[];
  /** Scans, not days — the axis is scans. */
  trendWindow?: number;
  height?: number;
}) {
  if (points.length === 0) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No scored scans yet. Your agents appear here once a scan has covered them.
      </p>
    );
  }

  const data = points.map((p, i) => {
    const window = points
      .slice(Math.max(0, i - (trendWindow - 1)), i + 1)
      .map((q) => q.avg_score);
    return {
      ...p,
      // Trailing, so the line never implies knowledge of scans that have not
      // run yet.
      trend: Math.round((window.reduce((a, b) => a + b, 0) / window.length) * 10) / 10,
    };
  });

  const label = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" })
      : "";

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
          <XAxis
            dataKey="captured_at"
            tickFormatter={(v) => label(String(v))}
            stroke="#94a3b8"
            fontSize={11}
            minTickGap={24}
          />
          <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 100]} allowDecimals={false} />
          <Tooltip
            content={<ChartTooltip />}
            labelFormatter={(v) => label(String(v))}
          />
          <Bar
            dataKey="avg_score"
            name="Average score"
            fill={GRADE_COLORS.B}
            radius={[2, 2, 0, 0]}
          />
          <Line
            type="monotone"
            dataKey="trend"
            name={`Trend (last ${trendWindow} scans)`}
            stroke="#64748b"
            strokeWidth={2}
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
