import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { AgentCreator, CreatorAgent } from "../api/types";
import DataTable, { applyFilters, type Column } from "../components/DataTable";
import KpiCard from "../components/KpiCard";
import PageHeader from "../components/PageHeader";
import { gradeColor, gradeForScore } from "../components/chartTheme";

/**
 * Who is making the agents, how good are they, and — when you pick one of them
 * — which agents those are.
 *
 * Named for what it actually is. The ask was for a tenant-users listing like
 * the sibling solutions have, and this app cannot build one — it holds no
 * directory data at all, because its worker reads Dataverse rather than Graph.
 * The only trace of a person in this schema is the maker Copilot Studio stamps
 * on an agent, so this lists people who have made one and says so on the page.
 *
 * Picking a creator filters this page rather than opening a page of their own.
 * That was a deliberate choice over a per-creator route: the question is "and
 * what are theirs, then?", asked while reading the table, and answering it
 * without leaving the table keeps the comparison in view. It is also why the
 * selection is *nothing more than* the table's own Creator filter with a value
 * in it — there is one filtering mechanism on this page, and a click is a
 * shortcut into it rather than a second one beside it.
 */

const GRADES = ["A", "B", "C", "D", "F"];

/** 60 is the C floor in engine/static_rules.py. Below it is a real signal. */
const C_FLOOR = 60;

/** The column the row click writes into. Named once: the click, the "clear"
 *  button and the filter box all have to agree about it. */
const CREATOR_COLUMN = "name";

function plural(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

/** A score with its grade letter beside it.
 *
 *  The letter is the judgement and it is spelled out, rather than being left
 *  to the colour of a chip — which this app's owner cannot read. */
function ScoreWithGrade({ score }: { score: number | null }) {
  if (score === null) return <span className="text-slate-400">–</span>;
  const grade = gradeForScore(score);
  return (
    <span className="inline-flex items-center justify-end gap-2">
      <span className="font-semibold text-slate-900 dark:text-slate-100">{score}</span>
      <span
        aria-hidden
        className="inline-grid h-5 w-5 place-items-center rounded text-[11px] font-bold text-white"
        style={{ background: gradeColor(grade) }}
      >
        {grade}
      </span>
      <span className="sr-only">grade {grade}</span>
    </span>
  );
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
  const nav = useNavigate();
  const [rows, setRows] = useState<AgentCreator[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // The filter row is driven from here rather than from inside the table, so
  // that the tiles above it and the agent list below it can be about the same
  // people the table is showing. A tile counting rows that are filtered out is
  // the failure this avoids.
  const [filters, setFilters] = useState<Record<string, string>>({});

  useEffect(() => {
    api
      .get<AgentCreator[]>("/reports/agent-creators")
      .then(setRows)
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoaded(true));
  }, []);

  /** Narrow the page to one person: write their stored UPN into the Creator
   *  filter and drop any other filter, so a click always lands on exactly the
   *  person clicked rather than on the intersection of them and whatever was
   *  already typed. */
  function selectCreator(r: AgentCreator) {
    setFilters({ [CREATOR_COLUMN]: r.upn });
  }

  const columns: Column<AgentCreator>[] = useMemo(
    () => [
      {
        key: CREATOR_COLUMN,
        header: "Creator",
        // Name over sign-in name in one column, the way the sidebar shows a
        // person. Two columns needed 1010px of table in a 974px space at a
        // 1280px window, which put Environments behind a horizontal scrollbar
        // on a very ordinary laptop. The filter still matches either, because
        // the accessor carries both — and it carries the *stored* UPN, so that
        // a row click can write an exact value into the box.
        accessor: (r) => `${r.display_name ?? ""} ${r.upn}`.trim(),
        render: (r) => (
          <div className="min-w-0">
            {/* A real button, not just a clickable row: this is the page's
                main action and it has to be reachable from the keyboard. The
                row is clickable too, for the mouse. */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                selectCreator(r);
              }}
              title={`Show only ${r.display_name || r.upn_display} and their agents`}
              className="block max-w-full truncate rounded text-left hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              {r.display_name || r.upn_display}
            </button>
            {r.display_name !== r.upn && (
              // The stored address is the tooltip, always. The visible form is
              // trimmed only for an unresolved creator carrying an object id in
              // front of their address, and only when what is left is a whole
              // address — so nothing here can invent one.
              <div
                className="truncate text-xs font-normal text-slate-400 dark:text-slate-500"
                title={r.upn_display === r.upn ? undefined : `Stored as ${r.upn}`}
              >
                {r.upn_display}
                {/* A creator the directory could not resolve is kept and shown
                    by sign-in address. Saying so is the difference between a
                    row that looks unfinished and one that is explained — they
                    may have left, or be a service principal that built an
                    agent. */}
                {!r.directory_resolved && " · not found in the directory"}
              </div>
            )}
          </div>
        ),
      },
      {
        key: "department",
        header: "Department",
        accessor: (r) => r.department ?? "",
        render: (r) =>
          r.department ?? (
            <span className="text-slate-400" title="No directory record for this creator">
              Unknown
            </span>
          ),
      },
      {
        key: "agents",
        header: "Agents",
        type: "number",
        align: "right",
        accessor: (r) => r.agents,
      },
      {
        key: "avg",
        // The scale is in the header. A bare "58" in a customer demo invites
        // somebody to read it as a percentage of something.
        header: "Avg score / 100",
        type: "number",
        align: "right",
        // Worst first on the first click. The page no longer opens in that
        // order, so "who needs help" has to stay one click away rather than
        // two — which is what a number column's usual high-to-low default
        // would have made it.
        defaultSortDir: "asc",
        accessor: (r) => r.avg_score,
        render: (r) => <ScoreWithGrade score={r.avg_score} />,
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
        key: "manager",
        header: "Manager",
        accessor: (r) => r.manager_name ?? "",
        render: (r) => r.manager_name ?? <span className="text-slate-400">—</span>,
      },
      {
        key: "environments",
        header: "Environments",
        accessor: (r) => r.environments.join(", "),
      },
    ],
    [],
  );

  const visibleRows = useMemo(
    () => applyFilters(rows, columns, filters),
    [rows, columns, filters],
  );

  const isFiltered = Object.values(filters).some((v) => v.trim());
  // One creator on screen is the selected-creator state, however it was
  // reached — a row click, or typing enough into any filter box to leave one
  // person. Both are the same question, so both get the same answer.
  //
  // It takes a filter as well as a single row, because a tenant with exactly
  // one recorded creator would otherwise open with their agents already
  // spilled out below and no banner explaining it — a page that looks like
  // somebody clicked something when nobody did.
  const selected = isFiltered && visibleRows.length === 1 ? visibleRows[0] : null;

  const stats = useMemo(() => {
    const of = (subset: AgentCreator[]) => {
      const agents = subset.reduce((n, r) => n + r.agents, 0);
      return {
        creators: subset.length,
        agents,
        environments: new Set(subset.flatMap((r) => r.environments)).size,
        departments: new Set(
          subset.map((r) => r.department).filter((d): d is string => Boolean(d)),
        ).size,
        needHelp: subset.filter(
          (r) => r.avg_score !== null && r.avg_score < C_FLOOR,
        ).length,
        findings: subset.reduce((n, r) => n + r.open_findings, 0),
        withFindings: subset.filter((r) => r.open_findings > 0).length,
        perCreator: subset.length ? (agents / subset.length).toFixed(1) : "0",
      };
    };
    // The tiles describe the rows on screen, not the tenant. They sit directly
    // above the table, so the alternative — leaving them tenant-wide while the
    // list beneath them is one person — is four numbers quietly about a
    // different population from everything under them. Each tile keeps the
    // tenant-wide figure in its hint while a filter is on, so the context is
    // not lost either.
    return { shown: of(visibleRows), all: of(rows) };
  }, [rows, visibleRows]);

  const { shown, all } = stats;

  if (err) return <div className="text-fail">{err}</div>;
  if (!loaded) return <div className="text-slate-500 dark:text-slate-400">Loading…</div>;

  return (
    <div className="space-y-6">
      <PageHeader title="Agent creators">
        Everyone Copilot Studio records as having created an agent, with how their agents
        score — <strong>click a name to see just their agents</strong>. Names and departments
        come from looking these people up in Entra — <em>only</em> these people. It is still
        not a tenant directory: somebody who has never made an agent is never looked up and
        does not appear here, and a creator the lookup cannot resolve is kept and listed by
        sign-in address rather than dropped.
      </PageHeader>

      {/* The filter is stated in words above everything it changes, and the way
          out of it is the button next to the words. A filter you cannot see is
          the reason a page looks broken; a filter you cannot leave is worse. */}
      {isFiltered && (
        <div className="card flex flex-wrap items-center justify-between gap-3 border-l-4 border-brand-500 px-5 py-3">
          <p className="text-sm text-slate-700 dark:text-slate-200">
            <span aria-hidden>● </span>
            {selected ? (
              <>
                Showing <strong>{selected.display_name || selected.upn_display}</strong>{" "}
                only — {plural(selected.agents, "agent")}, listed below.
              </>
            ) : (
              <>
                Filtered to <strong>{shown.creators}</strong> of{" "}
                {plural(all.creators, "creator")}.
              </>
            )}
          </p>
          <button type="button" className="btn-secondary text-sm" onClick={() => setFilters({})}>
            Show all creators
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Creators"
          value={shown.creators}
          hint={
            isFiltered
              ? `of ${plural(all.creators, "creator")} in the tenant`
              : shown.departments > 0
                ? `${plural(shown.departments, "department")}, ${plural(
                    shown.environments,
                    "environment",
                  )}`
                : `Across ${plural(shown.environments, "environment")}`
          }
        />
        <KpiCard
          label="Agents attributed"
          value={shown.agents}
          hint={
            isFiltered
              ? `of ${all.agents} across every creator`
              : `${shown.perCreator} per creator on average`
          }
        />
        <KpiCard
          label="Creators below a C average"
          value={shown.needHelp}
          hint={
            isFiltered
              ? `of ${all.needHelp} in the tenant · under ${C_FLOOR} out of 100`
              : shown.needHelp > 0
                ? `Averaging under ${C_FLOOR} out of 100`
                : "Everyone is at a C or better"
          }
        />
        <KpiCard
          label="Open findings"
          value={shown.findings}
          hint={
            isFiltered
              ? `of ${all.findings} across every creator`
              : shown.findings > 0
                ? `On ${shown.withFindings} of ${plural(shown.creators, "creator")}`
                : "Nothing outstanding"
          }
        />
      </div>

      <div className="card">
        {/* Alphabetical by name: this is a list of colleagues, and a list of
            people is looked *up* far more often than it is ranked. "Who needs
            help" is still one click — the Avg score header, which sorts worst
            first on that first click. filterable is opt-in per table: a list of
            people is the one table here long enough to need it. */}
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(r) => r.upn}
          initialSort={{ key: CREATOR_COLUMN, dir: "asc" }}
          filterable
          filters={filters}
          onFiltersChange={setFilters}
          onRowClick={selectCreator}
          emptyMessage="No agents have a recorded creator yet."
        />
      </div>

      {selected && (
        <CreatorAgents
          creator={selected}
          onOpen={(a) =>
            // A scorecard is a view of one scan, so an agent no scan has
            // reached yet has nothing to open. It is still listed — it is
            // theirs, and a creator's list that quietly omitted their newest
            // agent would be the worse bug — but the row says "not scored yet"
            // and does not pretend to go anywhere.
            a.bot_id &&
            a.scan_id != null &&
            nav(
              `/agents/${encodeURIComponent(a.bot_id)}?scan=${a.scan_id}&env=${
                a.environment_id ?? "demo"
              }`,
            )
          }
        />
      )}
    </div>
  );
}

/** The selected creator's agents, underneath the table they were picked from.
 *
 *  Same columns and same click-through as the Overview list, because it is the
 *  same thing seen through a narrower window — an agent row that behaved
 *  differently here would be a second idiom for no gain. */
function CreatorAgents({
  creator,
  onOpen,
}: {
  creator: AgentCreator;
  onOpen: (agent: CreatorAgent) => void;
}) {
  const columns: Column<CreatorAgent>[] = [
    { key: "agent", header: "Agent", accessor: (a) => a.agent_name ?? "" },
    {
      key: "environment",
      header: "Environment",
      accessor: (a) => a.environment_name ?? "",
    },
    {
      key: "solution",
      header: "Solution",
      accessor: (a) => a.solution_name ?? "",
      render: (a) =>
        a.solution_name ?? <span className="text-fail">default solution</span>,
    },
    {
      key: "state",
      header: "State",
      accessor: (a) => a.publish_state ?? "",
      className: "capitalize",
    },
    {
      key: "score",
      header: "Score / 100",
      type: "number",
      align: "right",
      defaultSortDir: "asc",
      accessor: (a) => a.score,
      render: (a) =>
        a.scan_id == null ? (
          // Said in words, not left as a dash: this row is the one that does
          // not open a scorecard, and the reason why is the cell itself.
          <span className="text-slate-400">Not scored yet</span>
        ) : (
          <ScoreWithGrade score={a.score} />
        ),
    },
    {
      key: "findings",
      header: "Open findings",
      type: "number",
      align: "right",
      accessor: (a) => a.open_findings,
    },
  ];

  const name = creator.display_name || creator.upn_display;
  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-brand-500 bg-brand-50 px-5 py-3 dark:bg-brand-500/10">
        <h2 className="font-semibold text-slate-900 dark:text-slate-100">
          {name}’s agents
          <span className="ml-2 text-sm font-normal text-slate-500 dark:text-slate-400">
            — worst score first; click one for its scorecard
          </span>
        </h2>
        <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
          {plural(creator.agent_list.length, "agent")}
        </span>
      </div>
      <DataTable
        columns={columns}
        rows={creator.agent_list}
        getRowKey={(a, i) => a.bot_id ?? `${a.agent_name}-${i}`}
        onRowClick={onOpen}
        // Dimmed, because clicking it does nothing — there is no scan behind it
        // to show. The "Not scored yet" in its Score cell is the words half of
        // the same signal.
        rowClassName={(a) => (a.scan_id == null ? "opacity-60" : "")}
        emptyMessage="No agents recorded for this creator."
      />
    </div>
  );
}
