import ChartCard from "./ChartCard";
import { gradeColor, gradeForScore } from "./chartTheme";
import type { PeerComparisonData, PeerSeries, TeamOmittedReason } from "../api/types";

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

/** Why there is no team series. Four different reasons, four different sentences.
 *
 *  `not_a_creator` matters most. The directory lookup is scoped to people who
 *  have built an agent — deliberately, because resolving everyone would be the
 *  tenant-wide sync this app refuses to do — so somebody who has built nothing
 *  has no directory row and therefore no team. Saying "your record has no
 *  department" there would blame the reader's Entra profile for a decision this
 *  app made. */
function teamNote(
  reason: TeamOmittedReason,
  teamSize: number,
): string {
  switch (reason) {
    case "too_small":
      return `No team comparison: your team is too small to show without identifying someone (${teamSize} other ${
        teamSize === 1 ? "person" : "people"
      } who have created agents). A team average next to your own figure would give their numbers away.`;
    case "unknown_team":
      return "No team comparison: your directory record has no department or manager, so there is no group to compare you with.";
    case "directory_unresolved":
      return "No team comparison: we have not been able to look you up in the directory yet. An administrator can run the creator lookup from Settings.";
    case "not_a_creator":
    default:
      return "No team comparison: you have not created an agent, so this report has no directory record for you. It looks up only the people who appear as agent creators — never the whole tenant — so there is nothing missing from your Entra profile.";
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
  const hasTeam = data.team !== null;
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
          const team = data.team ? data.team[m.key] : null;
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
          : teamNote(data.team_omitted_reason ?? "not_a_creator", data.team_size)}
      </p>
    </ChartCard>
  );
}
