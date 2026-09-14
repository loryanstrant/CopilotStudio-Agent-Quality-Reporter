import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { ScanRow, GRADE_COLORS } from "../api/types";

type SortKey = "started_at" | "environment" | "source" | "trigger" | "agent_count" | "avg_score" | "grade";

export default function HistoryPage() {
  const [scans, setScans] = useState<ScanRow[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("started_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    api.get<ScanRow[]>("/reports/scans").then(setScans).catch(() => setScans([]));
  }, []);

  const toggleSort = (k: SortKey) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir(k === "agent_count" || k === "avg_score" || k === "started_at" ? "desc" : "asc");
    }
  };

  const sorted = useMemo(() => {
    const rows = [...scans];
    rows.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      let cmp: number;
      if (typeof av === "number" || typeof bv === "number") {
        cmp = (av == null ? -Infinity : (av as number)) - (bv == null ? -Infinity : (bv as number));
      } else {
        cmp = String(av ?? "").localeCompare(String(bv ?? ""));
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [scans, sortKey, sortDir]);

  const Th = ({ label, k }: { label: string; k: SortKey }) => (
    <th
      className="py-2 pr-3 font-medium cursor-pointer select-none hover:text-slate-900 dark:hover:text-slate-100"
      onClick={() => toggleSort(k)}
    >
      {label}
      <span className="ml-1 text-xs">{sortKey === k ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span>
    </th>
  );

  return (
    <div className="space-y-6">
    <div>
      <h1 className="text-2xl font-bold">History</h1>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Every scan that has run, with the agents covered and the resulting score.
      </p>
    </div>
    <div className="card p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
        Scan history
      </h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
            <Th label="When" k="started_at" />
            <Th label="Environment" k="environment" />
            <Th label="Source" k="source" />
            <Th label="Trigger" k="trigger" />
            <Th label="Agents" k="agent_count" />
            <Th label="Avg" k="avg_score" />
            <Th label="Grade" k="grade" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => (
            <tr key={s.id} className="border-b border-slate-200 dark:border-slate-700">
              <td className="py-2 pr-3 text-slate-500 dark:text-slate-400 whitespace-nowrap">
                {s.started_at ? new Date(s.started_at).toLocaleString() : ""}
              </td>
              <td className="py-2 pr-3 text-slate-900 dark:text-slate-100">{s.environment}</td>
              <td className="py-2 pr-3 text-slate-500 dark:text-slate-400">{s.source}</td>
              <td className="py-2 pr-3 text-slate-500 dark:text-slate-400">{s.trigger}</td>
              <td className="py-2 pr-3 text-slate-500 dark:text-slate-400">{s.agent_count}</td>
              <td className="py-2 pr-3 font-semibold text-slate-900 dark:text-slate-100">{s.avg_score ?? "–"}</td>
              <td className="py-2 pr-3">
                {s.grade && (
                  <span className="pill text-white" style={{ background: GRADE_COLORS[s.grade] || "#8D99AE" }}>
                    {s.grade}
                  </span>
                )}
              </td>
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr>
              <td colSpan={7} className="py-6 text-center text-slate-500 dark:text-slate-400">
                No scans recorded yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      </div>
    </div>
  );
}
