import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { QualityTimeline, TimelineFilters } from "../api/types";
import ChartCard from "../components/ChartCard";
import MoversList from "../components/MoversList";
import QualityTrend from "../components/QualityTrend";

/**
 * How quality has moved — not what has run.
 *
 * This page used to be a table of scans, which was really a run log wearing the
 * History name. The run log now has its own page under ADMINISTRATION, and this
 * one answers the question the name promises: is quality getting better, and
 * what moved. Both read the `scans` table; they ask different things of it.
 */
export default function HistoryPage() {
  const [filters, setFilters] = useState<TimelineFilters | null>(null);
  const [data, setData] = useState<QualityTimeline | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [environmentId, setEnvironmentId] = useState<string>("");
  const [creatorUpn, setCreatorUpn] = useState<string>("");
  const [botId, setBotId] = useState<string>("");

  useEffect(() => {
    api
      .get<TimelineFilters>("/reports/timeline-filters")
      .then(setFilters)
      .catch(() => setFilters({ environments: [], creators: [], agents: [] }));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (environmentId) params.set("environment_id", environmentId);
    if (creatorUpn) params.set("creator_upn", creatorUpn);
    if (botId) params.set("bot_id", botId);
    const query = params.toString();
    setData(null);
    api
      .get<QualityTimeline>(`/reports/quality-timeline${query ? `?${query}` : ""}`)
      .then(setData)
      .catch((e) => setErr((e as Error).message));
  }, [environmentId, creatorUpn, botId]);

  const summary = useMemo(() => {
    const points = data?.points ?? [];
    if (points.length === 0) return null;
    const first = points[0];
    const last = points[points.length - 1];
    return {
      scans: points.length,
      latest: last.avg_score,
      change: last.avg_score - first.avg_score,
      spread: last.max_score - last.min_score,
      agents: last.agents,
    };
  }, [data]);

  const selectedCreator = filters?.creators.find((c) => c.upn === creatorUpn);

  if (err) return <div className="text-fail">{err}</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">History</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500 dark:text-slate-400">
          Average score over time, with the best and worst agent in each scan shaded behind
          it — so a rising average that hides one agent falling apart is visible. Looking for
          whether a scan ran? That is <strong>Scan history</strong>, under Administration.
        </p>
      </div>

      <div className="card flex flex-wrap items-end gap-4 p-4">
        <Picker
          label="Environment"
          value={environmentId}
          onChange={setEnvironmentId}
          allLabel="All environments"
          options={(filters?.environments ?? []).map((e) => ({
            value: String(e.id),
            label: e.label,
          }))}
        />
        <Picker
          label="Creator"
          value={creatorUpn}
          onChange={setCreatorUpn}
          allLabel="All creators"
          options={(filters?.creators ?? []).map((c) => ({
            value: c.upn,
            // Real names, because the creator directory resolves them. An
            // unresolved creator keeps their sign-in address rather than being
            // left out of the filter that is meant to find their agents.
            label: c.department ? `${c.label} · ${c.department}` : c.label,
          }))}
        />
        <Picker
          label="Agent"
          value={botId}
          onChange={setBotId}
          allLabel="All agents"
          options={(filters?.agents ?? []).map((a) => ({
            value: a.bot_id,
            label: a.label,
          }))}
        />
        {(environmentId || creatorUpn || botId) && (
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={() => {
              setEnvironmentId("");
              setCreatorUpn("");
              setBotId("");
            }}
          >
            Clear filters
          </button>
        )}
      </div>

      <ChartCard
        title="Average score over time"
        subtitle={
          summary
            ? `${summary.scans} scan${summary.scans === 1 ? "" : "s"} · latest average ${
                summary.latest
              }/100 across ${summary.agents} agent${summary.agents === 1 ? "" : "s"} · ${
                summary.change === 0
                  ? "no net change"
                  : `${summary.change > 0 ? "up" : "down"} ${Math.abs(
                      summary.change,
                    )} since the earliest scan shown`
              } · spread of ${summary.spread} between best and worst`
            : selectedCreator
              ? `${selectedCreator.label}'s agents`
              : "Every scored scan in the selection"
        }
      >
        {data ? (
          <QualityTrend points={data.points} />
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
        )}
      </ChartCard>

      <ChartCard
        title="Biggest movers"
        subtitle={
          data?.from_at && data?.to_at
            ? `Since each agent was last measured, up to ${new Date(
                data.to_at,
              ).toLocaleString()}`
            : "Since the previous scan"
        }
      >
        {data ? (
          <MoversList movers={data.movers} />
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
        )}
      </ChartCard>
    </div>
  );
}

function Picker({
  label,
  value,
  onChange,
  options,
  allLabel,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  allLabel: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-500 dark:text-slate-400">
      {label}
      <select
        className="input min-w-[14rem] text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{allLabel}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
