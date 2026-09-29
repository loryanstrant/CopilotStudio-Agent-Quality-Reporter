import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { AgentCreator } from "../api/types";
import DataTable, { type Column } from "../components/DataTable";
import KpiCard from "../components/KpiCard";
import { gradeColor, gradeForScore } from "../components/chartTheme";

/**
 * Who is making the agents, and how good are they.
 *
 * Named for what it actually is. The ask was for a tenant-users listing like
 * the sibling solutions have, and this app cannot build one — it holds no
 * directory data at all, because its worker reads Dataverse rather than Graph.
 * The only trace of a person in this schema is the maker Copilot Studio stamps
 * on an agent, so this lists people who have made one and says so on the page.
 */

const GRADES = ["A", "B", "C", "D", "F"];

/** 60 is the C floor in engine/static_rules.py. Below it is a real signal. */
const C_FLOOR = 60;

function plural(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

/** Grade spread as letter chips: "A×3 B×2".
 *
 *  The letter and the count are the content; the colour only reinforces them.
 *  A bar chart of five colours would have been prettier and unreadable to
 *  anyone who cannot tell the five apart — which includes this app's owner. */
function GradeSpread({ grades }: { grades: Record<string, number> }) {
  const present = GRADES.filter((g) => (grades[g] ?? 0) > 0);
  if (present.length === 0) {
    return <span className="text-slate-400">Not scored</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {present.map((g) => (
        <span
          key={g}
          title={`${plural(grades[g], "agent")} at grade ${g}`}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold text-white"
          style={{ background: gradeColor(g) }}
        >
          {g}
          <span className="font-normal opacity-90">×{grades[g]}</span>
        </span>
      ))}
    </div>
  );
}

export default function AgentCreatorsPage() {
  const [rows, setRows] = useState<AgentCreator[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api
      .get<AgentCreator[]>("/reports/agent-creators")
      .then(setRows)
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoaded(true));
  }, []);

  const stats = useMemo(() => {
    const agents = rows.reduce((n, r) => n + r.agents, 0);
    const environments = new Set(rows.flatMap((r) => r.environments));
    const needHelp = rows.filter(
      (r) => r.avg_score !== null && r.avg_score < C_FLOOR,
    ).length;
    const findings = rows.reduce((n, r) => n + r.open_findings, 0);
    const withFindings = rows.filter((r) => r.open_findings > 0).length;
    return {
      creators: rows.length,
      agents,
      environments: environments.size,
      needHelp,
      findings,
      withFindings,
      perCreator: rows.length ? (agents / rows.length).toFixed(1) : "0",
    };
  }, [rows]);

  const columns: Column<AgentCreator>[] = [
    {
      key: "name",
      header: "Creator",
      // Name over sign-in name in one column, the way the sidebar shows a
      // person. Two columns needed 1010px of table in a 974px space at a
      // 1280px window, which put Environments behind a horizontal scrollbar on
      // a very ordinary laptop. The filter still matches either, because the
      // accessor carries both.
      accessor: (r) => `${r.display_name ?? ""} ${r.upn}`.trim(),
      render: (r) => (
        <div className="min-w-0">
          <div className="truncate">{r.display_name || r.upn}</div>
          {r.display_name && (
            <div className="truncate text-xs font-normal text-slate-400 dark:text-slate-500">
              {r.upn}
            </div>
          )}
        </div>
      ),
    },
    { key: "agents", header: "Agents", type: "number", align: "right", accessor: (r) => r.agents },
    {
      key: "avg",
      // The scale is in the header. A bare "58" in a customer demo invites
      // somebody to read it as a percentage of something.
      header: "Avg score / 100",
      type: "number",
      align: "right",
      accessor: (r) => r.avg_score,
      render: (r) =>
        r.avg_score === null ? (
          <span className="text-slate-400">–</span>
        ) : (
          // The band is the judgement — "is this creator doing OK?" — so it is
          // spelled as a letter rather than left to the colour of the digits.
          <span className="inline-flex items-center justify-end gap-2">
            <span className="font-semibold text-slate-900 dark:text-slate-100">
              {r.avg_score}
            </span>
            <span
              aria-hidden
              className="inline-grid h-5 w-5 place-items-center rounded text-[11px] font-bold text-white"
              style={{ background: gradeColor(gradeForScore(r.avg_score)) }}
            >
              {gradeForScore(r.avg_score)}
            </span>
            <span className="sr-only">grade {gradeForScore(r.avg_score)}</span>
          </span>
        ),
    },
    {
      key: "spread",
      header: "Grade spread",
      // Wide enough for four chips on one line. Left to collapse, the cell
      // stacked them vertically and the row looked like an accident.
      className: "min-w-[11rem]",
      // Not sortable: a spread has no single order, and pretending otherwise
      // would sort on whichever grade happened to be read first.
      render: (r) => <GradeSpread grades={r.grades} />,
    },
    {
      key: "findings",
      header: "Open findings",
      type: "number",
      align: "right",
      accessor: (r) => r.open_findings,
    },
    {
      key: "environments",
      header: "Environments",
      accessor: (r) => r.environments.join(", "),
    },
  ];

  if (err) return <div className="text-fail">{err}</div>;
  if (!loaded) return <div className="text-slate-500 dark:text-slate-400">Loading…</div>;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
          Agent creators
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-500 dark:text-slate-400">
          Everyone Copilot Studio records as having created an agent, with how their agents
          score. This is built from the makers stamped on the agents themselves — it is not a
          tenant directory, so somebody who has never made an agent does not appear here.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Creators"
          value={stats.creators}
          hint={`Across ${plural(stats.environments, "environment")}`}
        />
        <KpiCard
          label="Agents attributed"
          value={stats.agents}
          hint={`${stats.perCreator} per creator on average`}
        />
        <KpiCard
          label="Creators below a C average"
          value={stats.needHelp}
          hint={
            stats.needHelp > 0
              ? `Averaging under ${C_FLOOR} out of 100`
              : "Everyone is at a C or better"
          }
        />
        <KpiCard
          label="Open findings"
          value={stats.findings}
          hint={
            stats.findings > 0
              ? `On ${stats.withFindings} of ${plural(stats.creators, "creator")}`
              : "Nothing outstanding"
          }
        />
      </div>

      <div className="card">
        {/* Worst average first, which is the question this page is opened to
            answer. filterable is opt-in per table: a list of people is the one
            table here long enough to need it. */}
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(r) => r.upn}
          initialSort={{ key: "avg", dir: "asc" }}
          filterable
          emptyMessage="No agents have a recorded creator yet."
        />
      </div>
    </div>
  );
}
