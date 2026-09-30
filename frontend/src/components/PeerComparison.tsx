import ChartCard from "./ChartCard";
import { gradeColor, gradeForScore } from "./chartTheme";
import type { PeerComparisonData, PeerSeries } from "../api/types";

interface Measure {
  key: keyof PeerSeries;
  label: string;
  /** How a value reads on its own — a count, or a score out of 100. */
  format: (value: number | null) => string;
  /** Drawn beside a score so the band is a letter, never a hue. */
  grade?: boolean;
}

const MEASURES: Measure[] = [
  {
    key: "agents",
    label: "Agents created",
    format: (v) => (v === null ? "–" : v.toLocaleString()),
  },
  {
    key: "avg_score",
    label: "Average score / 100",
    format: (v) => (v === null ? "Not scored" : String(v)),
    grade: true,
  },
];

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** The window all three series cover. Named, because three series over
 *  different periods would be arithmetically fine and thoroughly misleading. */
function fmtPeriod(from: string | null, to: string | null): string {
  if (!from && !to) return "all agents recorded so far";
  if (from && to) return `agents created ${fmtDate(from)} – ${fmtDate(to)}`;
  return from ? `agents created since ${fmtDate(from)}` : `up to ${fmtDate(to)}`;
}

function ordinal(n: number): string {
  const suffixes = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${suffixes[(v - 20) % 10] ?? suffixes[v] ?? suffixes[0]}`;
}

/** The sentence for a withheld team.
 *
 *  Told apart by `team_state`, never guessed from a peer count of zero: a
 *  department of one and a record with no department both have no peers, and
 *  saying "we don't know which team you're in" to somebody whose department is on
 *  file is a false statement about their own data that points an administrator at
 *  the wrong problem.
 *
 *  The floor comes from the response, so this copy cannot drift away from the
 *  rule the endpoint applied.
 *
 *  `no_directory_record` is the case specific to this app, and the reason its
 *  sentence offers no remedy: the creator lookup covers people who have built an
 *  agent and nobody else, so there is nothing for an administrator to populate.
 *  Telling this reader to fill in a department in Entra would be advice that
 *  cannot work — their Entra record may be perfect and they would still see two
 *  series. */
function withheldNote(data: PeerComparisonData): string {
  if (data.team_state === "too_small") {
    const who =
      data.team_size === 0
        ? `you are the only person in ${data.team_label ?? "your team"} who has created an agent`
        : `${data.team_label ?? "your team"} has ${data.team_size} other ${
            data.team_size === 1 ? "person" : "people"
          } who have created agents`;
    return `No team comparison — ${who}, and a team average is only shown from ${data.min_team_peers}. Below that, the average and your own figure together would give an individual's number away.`;
  }
  switch (data.team_unknown_reason) {
    case "no_directory_record":
      return "No team comparison — you have not created an agent, so this report has never looked you up. It only ever looks up the people recorded as agent creators, never the whole tenant, so there is nothing missing from your directory record and nothing an administrator needs to change.";
    case "lookup_incomplete":
      return "No team comparison — the directory lookup has not resolved your account yet. An administrator can run it from Settings, which also reports whether the User.Read.All permission has been granted.";
    default:
      return "No team comparison — we don't know which team you're in, because your directory record has no department and no manager. Populating either in Entra will fill this in.";
  }
}

/**
 * You, your team and your organisation on the same two measures.
 *
 * The team row is **absent** when the server withholds it, never a zero bar: an
 * empty bar reads as "you are miles ahead of your team" when it means "that
 * group is too small to show without identifying somebody".
 */
export default function PeerComparison({ data }: { data: PeerComparisonData }) {
  // The server states this; the component never re-decides it.
  const hasTeam = data.team_state === "shown" && data.team !== null;
  const subtitle = [
    hasTeam
      ? `You, your team (${data.team_label}) and the organisation`
      : "You and the organisation",
    fmtPeriod(data.period_from, data.period_to),
  ].join(" · ");

  return (
    <ChartCard title="How you compare" subtitle={subtitle}>
      <div className="space-y-5 text-sm">
        {MEASURES.map((m) => {
          const mine = data.mine[m.key];
          // Follows the stated state, so a team series can never appear
          // because a payload carried figures the state said to withhold.
          const team = hasTeam && data.team ? data.team[m.key] : null;
          const org = data.organisation[m.key];
          const max = Math.max(mine ?? 0, team ?? 0, org ?? 0, 1);
          const pct = data.percentile[m.key];
          const rows: { label: string; value: number | null; bar: string }[] = [
            { label: "You", value: mine, bar: "bg-brand-600" },
            ...(team !== null
              ? [{ label: `Your team`, value: team, bar: "bg-brand-300" }]
              : []),
            { label: "Organisation", value: org, bar: "bg-slate-400" },
          ];
          return (
            <div key={m.key}>
              <div className="mb-1 flex items-baseline justify-between gap-3">
                <span className="font-medium text-slate-800 dark:text-slate-100">
                  {m.label}
                </span>
                {pct !== null && (
                  <span className="text-xs text-slate-400 dark:text-slate-500">
                    {/* The population is stated: a team of six makes a
                        team-relative percentile arithmetic, not information. */}
                    {ordinal(pct)} percentile across the organisation
                  </span>
                )}
              </div>
              <div className="space-y-1">
                {rows.map((r) => (
                  <div key={r.label} className="flex items-center gap-2">
                    <span className="w-28 shrink-0 text-xs text-slate-500 dark:text-slate-400">
                      {r.label}
                    </span>
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
                      <div
                        className={`h-full rounded-full ${r.bar}`}
                        style={{
                          width: `${Math.max(((r.value ?? 0) / max) * 100, 2)}%`,
                        }}
                      />
                    </div>
                    <span className="flex w-24 shrink-0 items-center justify-end gap-1.5 text-right text-xs tabular-nums text-slate-600 dark:text-slate-300">
                      {m.format(r.value)}
                      {m.grade && r.value !== null && (
                        <>
                          <span
                            aria-hidden
                            className="inline-grid h-4 w-4 place-items-center rounded text-[10px] font-bold text-white"
                            style={{
                              background: gradeColor(gradeForScore(r.value)),
                            }}
                          >
                            {gradeForScore(r.value)}
                          </span>
                          <span className="sr-only">
                            grade {gradeForScore(r.value)}
                          </span>
                        </>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-4 text-xs text-slate-400 dark:text-slate-500">
        {hasTeam
          ? `Averages only, never individual figures. Your team is ${data.team_size} other ${
              data.team_size === 1 ? "person" : "people"
            } who have created agents; the organisation is ${data.organisation_size}.`
          : withheldNote(data)}
      </p>
    </ChartCard>
  );
}
