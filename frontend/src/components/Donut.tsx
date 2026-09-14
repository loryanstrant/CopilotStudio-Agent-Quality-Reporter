import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";

interface Slice {
  label: string;
  value: number;
  color: string;
}

/** Check-outcome breakdown. Recharts pie with a centred total, plus a legend
 *  list so the exact counts stay readable at small sizes. */
export default function Donut({ slices }: { slices: Slice[] }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  // Recharts renders nothing for an all-zero dataset, so fall back to a single
  // neutral ring that still shows the (zero) total.
  const data = total > 0 ? slices : [{ label: "No checks", value: 1, color: "#cbd5e1" }];

  return (
    <div className="flex items-center gap-5">
      <div className="relative h-[150px] w-[150px] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="label"
              innerRadius={48}
              outerRadius={66}
              startAngle={90}
              endAngle={-270}
              stroke="none"
              isAnimationActive={false}
            >
              {data.map((s, i) => (
                <Cell key={i} fill={s.color} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{total}</div>
          <div className="text-[10px] text-slate-500 dark:text-slate-400">checks</div>
        </div>
      </div>
      <ul className="space-y-1 text-sm">
        {slices.map((s, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-sm" style={{ background: s.color }} />
            <span className="text-slate-500 dark:text-slate-400">{s.label}</span>
            <span className="ml-auto font-semibold text-slate-900 dark:text-slate-100">
              {s.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
