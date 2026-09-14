import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { GRADE_COLORS, MyAgentCard, MySummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import KpiCard from "../components/KpiCard";

function GradeBadge({ grade }: { grade: string | null }) {
  if (!grade) return <span className="text-slate-500 dark:text-slate-400">–</span>;
  return (
    <span
      className="inline-grid h-7 w-7 place-items-center rounded-full text-sm font-bold text-white"
      style={{ background: GRADE_COLORS[grade] || "#8D99AE" }}
    >
      {grade}
    </span>
  );
}

function ScoreBar({ score }: { score: number | null }) {
  const v = score ?? 0;
  const color = v >= 75 ? "#2A9D8F" : v >= 60 ? "#E9C46A" : v >= 40 ? "#F4A261" : "#E63946";
  return (
    <div className="flex min-w-[120px] items-center gap-2">
      <div className="h-2 flex-1 rounded bg-slate-200 dark:bg-slate-700">
        <div className="h-2 rounded" style={{ width: `${v}%`, background: color }} />
      </div>
      <span className="w-8 text-right text-sm font-semibold text-slate-900 dark:text-slate-100">
        {score ?? "–"}
      </span>
    </div>
  );
}

/** The step across to organisation-wide reporting.
 *
 *  When the person is not in the organisation view group the control is shown
 *  but disabled, rather than hidden. Hiding it makes the product look broken
 *  ("where did the dashboard go?"); showing it locked explains what happened
 *  and who to ask. */
function OrgViewBanner({ canViewOrg }: { canViewOrg: boolean }) {
  if (canViewOrg) {
    return (
      <Link to="/org" className="btn-secondary text-sm">
        View all agents →
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        disabled
        title="Organisation-wide reporting is limited to an approved group."
        className="cursor-not-allowed rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-400 dark:border-slate-600 dark:text-slate-500"
      >
        🔒 All agents
      </button>
      <span className="text-xs text-slate-500 dark:text-slate-400">
        Organisation-wide reporting is limited to an approved group — ask your administrator if
        you need access.
      </span>
    </div>
  );
}

export default function PersonalPage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [summary, setSummary] = useState<MySummary | null>(null);
  const [agents, setAgents] = useState<MyAgentCard[]>([]);
  const [err, setErr] = useState<string | null>(null);

  // No user id is passed here, and none is accepted: the API reads the person
  // from the token. A page that named its user would let anyone read anyone
  // else's agents by editing the URL.
  useEffect(() => {
    if (!user?.has_personal_view) return;
    Promise.all([
      api.get<MySummary>("/reports/me/summary"),
      api.get<MyAgentCard[]>("/reports/me/agents"),
    ])
      .then(([s, a]) => {
        setSummary(s);
        setAgents(a);
      })
      .catch((e) => setErr((e as Error).message));
  }, [user?.has_personal_view]);

  // The password admin has no directory identity, so there is nothing personal
  // to show them.
  if (!user?.has_personal_view) {
    return (
      <div className="card p-6 text-sm text-slate-500 dark:text-slate-400">
        Sign in with your work account to see the agents you created.
      </div>
    );
  }

  if (err) return <div className="text-fail">{err}</div>;
  if (!summary) return <div className="text-slate-500 dark:text-slate-400">Loading…</div>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
            Your agents
          </h2>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Agents created by {user.username}, with their latest quality score and anything still
            open.
          </p>
        </div>
        <OrgViewBanner canViewOrg={user.can_view_org} />
      </div>

      {!summary.has_data ? (
        <div className="card p-8 text-center">
          <div className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            No agents yet
          </div>
          <p className="mx-auto mt-2 max-w-xl text-sm text-slate-500 dark:text-slate-400">
            Nothing in the most recent scans was created by your account. Agents appear here once
            they have been scanned and Copilot Studio records you as their maker.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard label="Agents you created" value={summary.agents} />
            <KpiCard
              label="Average score"
              value={summary.avg_score ?? "–"}
              hint={`${summary.scored_agents} scored`}
            />
            <KpiCard label="Lowest grade" value={summary.worst_grade ?? "–"} />
            <KpiCard
              label="Open findings"
              value={summary.open_findings}
              hint="Across your agents"
            />
          </div>

          <div className="card p-5">
            <h3 className="mb-3 font-semibold text-slate-900 dark:text-slate-100">
              Your agents ({agents.length})
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    <th className="py-2 pr-4">Agent</th>
                    <th className="py-2 pr-4">Environment</th>
                    <th className="py-2 pr-4">State</th>
                    <th className="py-2 pr-4">Score</th>
                    <th className="py-2 pr-4">Grade</th>
                    <th className="py-2 pr-4">Open findings</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map((a) => (
                    <tr
                      key={a.bot_id || a.agent_name}
                      onClick={() =>
                        a.bot_id &&
                        a.scan_id &&
                        nav(`/agents/${encodeURIComponent(a.bot_id)}?scan=${a.scan_id}`)
                      }
                      className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60"
                    >
                      <td className="py-2 pr-4 font-medium text-slate-900 dark:text-slate-100">
                        {a.agent_name}
                      </td>
                      <td className="py-2 pr-4 text-slate-500 dark:text-slate-400">
                        {a.environment_name || "–"}
                      </td>
                      <td className="py-2 pr-4 text-slate-500 dark:text-slate-400">
                        {a.publish_state || "–"}
                      </td>
                      <td className="py-2 pr-4">
                        <ScoreBar score={a.score} />
                      </td>
                      <td className="py-2 pr-4">
                        <GradeBadge grade={a.grade} />
                      </td>
                      <td className="py-2 pr-4 tabular-nums text-slate-900 dark:text-slate-100">
                        {a.open_findings}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
