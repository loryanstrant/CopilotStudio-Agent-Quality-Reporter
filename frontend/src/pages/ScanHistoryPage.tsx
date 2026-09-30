import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { RunLogRow } from "../api/types";
import ChartCard from "../components/ChartCard";
import DataTable, { type Column } from "../components/DataTable";
import { gradeColor } from "../components/chartTheme";

/**
 * The run log: did it run, and what did it write.
 *
 * Distinct from History, which is the quality trend — and the two do read the
 * same table, so the wording on both pages says which question it answers. In
 * this app the run log has always been `scans`: the worker has written it since
 * the first release, while `job_runs` was declared and never used until the
 * creator directory sync arrived. Both are listed here, sorted together.
 */

/** Shape plus word, never colour alone. */
const STATE: Record<string, { mark: string; word: string }> = {
  succeeded: { mark: "●", word: "Succeeded" },
  running: { mark: "◐", word: "In progress" },
  failed: { mark: "○", word: "Failed" },
  cancelled: { mark: "○", word: "Cancelled" },
};

function fmtWhen(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m < 60 ? `${m}m ${String(s).padStart(2, "0")}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

// The stats blob is keyed by column names. Left raw it reads as "14 creators
// resolved 13", which is the schema talking rather than the product.
const STAT_LABEL: Record<string, [string, string]> = {
  creators: ["creator looked up", "creators looked up"],
  resolved: ["resolved", "resolved"],
  unresolved: ["not in the directory", "not in the directory"],
  lookup_errors: ["lookup error", "lookup errors"],
  agents: ["agent", "agents"],
};

function fmtWrote(row: RunLogRow): string {
  // A scan has better columns than a stats blob, so it gets a sentence built
  // from them: "18 agents · score 63 (C)" says more than a row count.
  if (row.scan_id !== null) {
    const parts: string[] = [];
    if (row.agents_found !== null) {
      parts.push(
        `${row.agents_found} agent${row.agents_found === 1 ? "" : "s"}${
          row.partial ? ` (${row.agents_scored} scored)` : ""
        }`,
      );
    }
    if (row.score !== null) {
      parts.push(`score ${row.score}${row.grade ? ` (${row.grade})` : ""}`);
    }
    return parts.length ? parts.join(" · ") : "—";
  }
  const parts = Object.entries(row.wrote)
    .filter(([, v]) => typeof v === "number")
    .map(([k, v]) => {
      const n = Number(v);
      const words = STAT_LABEL[k];
      const word = words ? (n === 1 ? words[0] : words[1]) : k.replace(/_/g, " ");
      return `${n.toLocaleString()} ${word}`;
    });
  return parts.length ? parts.join(" · ") : "—";
}

export default function ScanHistoryPage() {
  const [rows, setRows] = useState<RunLogRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<RunLogRow[]>("/admin/scan-history")
      .then(setRows)
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoaded(true));
  }, []);

  const columns: Column<RunLogRow>[] = useMemo(
    () => [
      {
        key: "started_at",
        header: "Started",
        type: "date",
        accessor: (r) => r.started_at,
        render: (r) => (
          <span className="whitespace-nowrap">{fmtWhen(r.started_at)}</span>
        ),
      },
      { key: "kind", header: "Kind", accessor: (r) => r.kind },
      {
        key: "environment",
        header: "Environment",
        accessor: (r) => r.environment ?? "",
        render: (r) =>
          r.environment ?? <span className="text-slate-400">Whole tenant</span>,
      },
      {
        key: "state",
        header: "Status",
        accessor: (r) => STATE[r.state]?.word ?? r.raw_status,
        render: (r) => {
          const s = STATE[r.state];
          return (
            <span className="whitespace-nowrap">
              {/* An unmapped status keeps its raw value rather than vanishing. */}
              <span aria-hidden>{s ? `${s.mark} ` : ""}</span>
              {s ? s.word : r.raw_status}
              {r.partial && (
                <span className="ml-1 text-xs text-amber-700 dark:text-amber-300">
                  · part-finished
                </span>
              )}
            </span>
          );
        },
      },
      {
        key: "duration_seconds",
        header: "Took",
        type: "number",
        align: "right",
        accessor: (r) => r.duration_seconds,
        render: (r) => fmtDuration(r.duration_seconds),
        filterable: false,
      },
      {
        key: "wrote",
        header: "What it wrote",
        accessor: (r) => fmtWrote(r),
        render: (r) => (
          <span className="inline-flex items-center gap-2">
            {fmtWrote(r)}
            {r.grade && (
              <>
                <span
                  aria-hidden
                  className="inline-grid h-5 w-5 place-items-center rounded text-[11px] font-bold text-white"
                  style={{ background: gradeColor(r.grade) }}
                >
                  {r.grade}
                </span>
                <span className="sr-only">grade {r.grade}</span>
              </>
            )}
          </span>
        ),
      },
      {
        key: "error",
        header: "Detail",
        accessor: (r) => r.error ?? "",
        render: (r) =>
          r.error ? (
            <span className="text-rose-700 dark:text-rose-400">{r.error}</span>
          ) : (
            <span className="text-slate-400">—</span>
          ),
      },
    ],
    [],
  );

  const counts = useMemo(() => {
    const failed = rows.filter((r) => r.state === "failed").length;
    const partial = rows.filter((r) => r.partial).length;
    return { failed, partial };
  }, [rows]);

  if (err) return <div className="text-fail">{err}</div>;
  if (!loaded) return <div className="text-slate-500 dark:text-slate-400">Loading…</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          Scan history
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500 dark:text-slate-400">
          Every scan and directory lookup this deployment has run, newest first — what kind it
          was, how long it took, what it wrote and whether it worked. For how quality has
          moved over time, see <strong>History</strong>.
        </p>
      </div>

      <ChartCard
        title={`${rows.length.toLocaleString()} run${rows.length === 1 ? "" : "s"}`}
        subtitle={
          rows.length === 0
            ? "Scheduled scans, manual scans and creator directory lookups"
            : [
                `${counts.failed} failed`,
                counts.partial > 0 ? `${counts.partial} part-finished` : null,
              ]
                .filter(Boolean)
                .join(" · ")
        }
        className="px-0"
      >
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(r) => r.id}
          initialSort={{ key: "started_at", dir: "desc" }}
          filterable
          maxBodyHeight={620}
          emptyMessage="Nothing has run yet. Open Settings and use Scan now, or wait for the next scheduled scan."
        />
      </ChartCard>
    </div>
  );
}
