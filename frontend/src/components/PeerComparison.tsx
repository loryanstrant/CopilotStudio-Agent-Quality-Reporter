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
/** What the comparison population actually is, in this app.
 *
 *  Not the tenant. It is people recorded as having created an agent and resolved
 *  through the directory, which in a real customer is tens of people inside a
 *  tenant of thousands. Calling that bar "Organisation" invites the reader to
 *  think they are being compared with their colleagues at large, and they are
 *  not — so it is labelled for what it is, and the withheld sentence counts
 *  creators rather than describing the tenant as small. */
const ORG_LABEL = "All agent creators";

/** The sentence for a withheld organisation series.
 *
 *  A mean plus the reader's own figure identifies somebody whatever the group is
 *  called, so the same floor applies here — and it will be reached far more often
 *  in this app than in its siblings, because the population is creators rather
 *  than everyone with a licence. The copy therefore never says "your tenant is
 *  small": a five-thousand-person tenant with four people building agents lands
 *  here, and telling them their organisation is too small would be false. */
function organisationWithheldNote(data: PeerComparisonData): string {
  const others = data.organisation_size;
  const who =
    others === 0
      ? "you are the only person who has created an agent"
      : `only ${others + 1} people have created an agent`;
  return `No comparison with other creators — ${who}, and an average is only shown from ${
    data.min_team_peers
  } others. Below that, the average and your own figure together would identify somebody. Your own figures are above; the percentile is held back for the same reason.`;
}

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
  const hasOrg = data.organisation_state === "shown" && data.organisation !== null;
  const subtitle = [
    hasTeam && hasOrg
      ? `You, your team (${data.team_label}) and everyone who has created an agent`
      : hasOrg
        ? "You and everyone who has created an agent"
        : hasTeam
          ? `You and your team (${data.team_label})`
          : "Your own figures",
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
          const org = hasOrg && data.organisation ? data.organisation[m.key] : null;
          const max = Math.max(mine ?? 0, team ?? 0, org ?? 0, 1);
          const pct = data.percentile[m.key];
          const rows: { label: string; value: number | null; bar: string }[] = [
            { label: "You", value: mine, bar: "bg-brand-600" },
            ...(team !== null
              ? [{ label: `Your team`, value: team, bar: "bg-brand-300" }]
              : []),
            ...(org !== null
              ? [{ label: ORG_LABEL, value: org, bar: "bg-slate-400" }]
              : []),
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
                        team-relative percentile arithmetic, not information —
                        and in this app the wider group is agent creators, not
                        the tenant, which the wording has to admit. */}
                    {ordinal(pct)} percentile among agent creators
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
            } who have created agents, out of ${data.organisation_size} in total.`
          : withheldNote(data)}
      </p>
      {!hasOrg && (
        <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
          {organisationWithheldNote(data)}
        </p>
      )}
    </ChartCard>
  );
}
