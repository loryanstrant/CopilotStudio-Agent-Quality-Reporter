import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { Briefing, BriefingPeriod } from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import KpiCard from "../components/KpiCard";
import { CHART_COLORS, gradId, gradeColor, sevColor } from "../components/chartTheme";

/**
 * The executive briefing.
 *
 * Deliberately deterministic. Every figure comes from SQL and every sentence is
 * assembled here from fixed thresholds — there is no model in this path, even
 * though the app has Azure OpenAI configured for the instruction judge. A
 * briefing is the artefact most likely to be read aloud to a customer, and it
 * must never be able to invent a number.
 */

type Tone = "positive" | "negative" | "neutral";

const GRADES = ["A", "B", "C", "D", "F"];
const SEVERITIES = ["blocker", "major", "minor", "info"];

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function plural(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

/** Score movement is in points, not per cent: a score is already out of 100,
 *  so "up 4 points" is what a reader can act on and "up 6%" is not. */
function points(cur: number | null, prev: number | null): number | null {
  if (cur === null || prev === null) return null;
  return cur - prev;
}

function movementWord(d: number): string {
  if (d === 0) return "unchanged";
  return `${d > 0 ? "up" : "down"} ${Math.abs(d)}`;
}

function countDelta(cur: number, prev: number): number | null {
  if (prev === 0 && cur === 0) return 0;
  return cur - prev;
}

/** Shape, then word. Never colour alone — the tone marks here repeat in text. */
function toneMark(t: Tone): string {
  return t === "positive" ? "▲" : t === "negative" ? "▼" : "■";
}

function toneClass(t: Tone): string {
  return t === "positive"
    ? "text-pass"
    : t === "negative"
      ? "text-fail"
      : "text-slate-400";
}

function buildNarrative(b: Briefing): { tone: Tone; text: string }[] {
  const out: { tone: Tone; text: string }[] = [];
  const cur = b.current;
  const prev = b.previous;
  const end = b.period_end ? fmtDate(b.period_end) : "the latest scan";

  const dScore = points(cur.avg_score, prev.avg_score);
  const trend =
    dScore === null
      ? ", with no comparable scan in the period before it"
      : dScore === 0
        ? ", unchanged against the previous period"
        : `, ${movementWord(dScore)} ${Math.abs(dScore) === 1 ? "point" : "points"} on the previous period`;
  out.push({
    tone: dScore === null ? "neutral" : dScore >= 0 ? "positive" : "negative",
    text: `As at ${end}, ${plural(cur.agents, "agent")} across ${plural(
      cur.environments,
      "environment",
    )} scored an average of ${cur.avg_score ?? "–"} out of 100${trend}.`,
  });

  const passing = (cur.grades.A ?? 0) + (cur.grades.B ?? 0);
  const failing = cur.grades.F ?? 0;
  const share = cur.agents ? Math.round((passing / cur.agents) * 100) : 0;
  out.push({
    tone: share >= 60 ? "positive" : share >= 30 ? "neutral" : "negative",
    text:
      `${plural(passing, "agent")} (${share}%) hold an A or a B` +
      (failing > 0
        ? `, and ${plural(failing, "agent")} ${failing === 1 ? "is" : "are"} failing outright at grade F.`
        : ", and none is failing outright."),
  });

  const dFindings = countDelta(cur.open_findings, prev.open_findings);
  const blockers = cur.findings_by_severity.blocker ?? 0;
  const findingsMove =
    dFindings === null || dFindings === 0
      ? ""
      : ` — ${Math.abs(dFindings)} ${dFindings > 0 ? "more" : "fewer"} than last period`;
  out.push({
    tone: blockers > 0 ? "negative" : dFindings !== null && dFindings <= 0 ? "positive" : "neutral",
    text:
      `${plural(cur.open_findings, "finding")} ${cur.open_findings === 1 ? "is" : "are"} open${findingsMove}` +
      (blockers > 0
        ? `, including ${plural(blockers, "blocker")}.`
        : ", none of them blockers."),
  });

  const worst = b.worst_agents[0];
  if (worst) {
    out.push({
      tone: "negative",
      text: `The lowest-scoring agent is ${worst.agent_name} at ${worst.score} (grade ${worst.grade}).`,
    });
  }

  return out;
}

function buildHighlights(b: Briefing): string[] {
  const items: string[] = [];
  const cur = b.current;
  const dScore = points(cur.avg_score, b.previous.avg_score);
  if (dScore !== null && dScore > 0)
    items.push(`Average score ${movementWord(dScore)} points period-on-period.`);
  const dFindings = countDelta(cur.open_findings, b.previous.open_findings);
  if (dFindings !== null && dFindings < 0)
    items.push(`${Math.abs(dFindings)} fewer open findings than last period.`);
  if ((cur.grades.A ?? 0) > 0)
    items.push(`${plural(cur.grades.A, "agent")} scoring an A.`);
  if ((cur.findings_by_severity.blocker ?? 0) === 0)
    items.push("No blocker-severity findings anywhere.");
  if (cur.environments > 1)
    items.push(`Coverage across ${plural(cur.environments, "environment")}.`);
  return items.slice(0, 5);
}

function buildWatchouts(b: Briefing): string[] {
  const items: string[] = [];
  const cur = b.current;
  const dScore = points(cur.avg_score, b.previous.avg_score);
  if (dScore !== null && dScore < 0)
    items.push(`Average score ${movementWord(dScore)} points versus the previous period.`);
  const blockers = cur.findings_by_severity.blocker ?? 0;
  if (blockers > 0) items.push(`${plural(blockers, "blocker-severity finding")} open.`);
  const failing = (cur.grades.D ?? 0) + (cur.grades.F ?? 0);
  if (failing > 0) items.push(`${plural(failing, "agent")} at grade D or F.`);
  const rule = b.top_rules[0];
  if (rule) items.push(`"${rule.name}" fails on ${plural(rule.agents, "agent")}.`);
  const dFindings = countDelta(cur.open_findings, b.previous.open_findings);
  if (dFindings !== null && dFindings > 0)
    items.push(`${dFindings} more open findings than last period.`);
  return items.slice(0, 5);
}

function buildActions(b: Briefing): string[] {
  const items: string[] = [];
  const rule = b.top_rules[0];
  if (rule)
    items.push(
      `Fix "${rule.name}" once and it clears on ${plural(rule.agents, "agent")} — the single biggest win available.`,
    );
  const worst = b.worst_agents[0];
  if (worst) items.push(`Review ${worst.agent_name} (${worst.score}/100) with its maker.`);
  const blockers = b.current.findings_by_severity.blocker ?? 0;
  if (blockers > 0)
    items.push(`Clear the ${plural(blockers, "blocker")} before anything else — they carry the most weight.`);
  if ((b.current.grades.F ?? 0) > 0)
    items.push("Agree a remediation date for every agent at grade F.");
  items.push("Use Agent creators to see which makers need the most support.");
  return items.slice(0, 5);
}

export default function BriefingPage() {
  const [b, setB] = useState<Briefing | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api
      .get<Briefing>("/reports/briefing")
      .then(setB)
      .catch(() => undefined)
      .finally(() => setLoaded(true));
  }, []);

  const narrative = useMemo(() => (b ? buildNarrative(b) : []), [b]);
  const highlights = useMemo(() => (b ? buildHighlights(b) : []), [b]);
  const watchouts = useMemo(() => (b ? buildWatchouts(b) : []), [b]);
  const actions = useMemo(() => (b ? buildActions(b) : []), [b]);
  const trend = useMemo(() => (b ? b.trend.slice(-60) : []), [b]);
  const generatedAt = useMemo(
    () => new Date().toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }),
    [],
  );

  if (!loaded) {
    return <div className="text-slate-500 dark:text-slate-400">Preparing briefing…</div>;
  }

  if (!b || !b.has_data) {
    return (
      <div className="space-y-6">
        <Header period="" generatedAt={generatedAt} />
        <div className="card p-6 text-sm text-slate-500 dark:text-slate-400">
          No scan data yet. Add an environment in Settings and run a scan — or load demo
          data — to generate your first briefing.
        </div>
      </div>
    );
  }

  const cur = b.current;
  const dScore = points(cur.avg_score, b.previous.avg_score);
  const dAgents = countDelta(cur.agents, b.previous.agents);
  const dFindings = countDelta(cur.open_findings, b.previous.open_findings);

  return (
    <div className="space-y-8">
      <Header
        period={`${b.window_days} days to ${b.period_end ? fmtDate(b.period_end) : "–"}`}
        generatedAt={generatedAt}
      />

      {/* The narrative is the briefing. Everything below it is evidence. */}
      <div className="card border-l-4 border-l-brand-500 p-6">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">
          <span>Summary</span>
          <span className="text-slate-300 dark:text-slate-600">•</span>
          <span className="font-normal normal-case text-slate-400">
            Calculated from your scans — no model, no estimates
          </span>
        </div>
        <div className="space-y-2.5">
          {narrative.map((p, i) => (
            <p
              key={i}
              className="flex gap-2 text-[15px] leading-relaxed text-slate-700 dark:text-slate-200"
            >
              <span aria-hidden className={`mt-1 text-xs ${toneClass(p.tone)}`}>
                {toneMark(p.tone)}
              </span>
              <span>{p.text}</span>
            </p>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Average score"
          value={cur.avg_score ?? "–"}
          hint={deltaHint(dScore, "point")}
        />
        <KpiCard
          label="Agents scanned"
          value={cur.agents}
          hint={deltaHint(dAgents, "agent")}
        />
        <KpiCard
          label="Open findings"
          value={cur.open_findings}
          hint={deltaHint(dFindings, "finding")}
        />
        <KpiCard
          label="Environments"
          value={cur.environments}
          hint={`${plural(cur.grades.F ?? 0, "agent")} at grade F`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <ChartCard
          title="Momentum"
          subtitle="Average agent score by day, last 60 days"
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={trend} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                stroke="#94a3b8"
                tickMargin={8}
                minTickGap={24}
              />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" domain={[0, 100]} />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="avg_score"
                name="Average score"
                stroke={CHART_COLORS[0]}
                strokeWidth={2.5}
                fill={`url(#${gradId(0)})`}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <GradeMix period={cur} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ListCard
          title="Highlights"
          tone="positive"
          items={highlights}
          empty="Nothing notable this period."
        />
        <ListCard
          title="Watch-outs"
          tone="negative"
          items={watchouts}
          empty="No concerns flagged."
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Most common failures" subtitle="Rules failing on the most agents">
          {b.top_rules.length === 0 ? (
            <p className="text-sm text-slate-400">Nothing failing.</p>
          ) : (
            <ul className="space-y-3">
              {b.top_rules.map((r) => (
                <li key={r.rule_id} className="flex items-center gap-3 text-sm">
                  <SeverityTag severity={r.severity} />
                  <span className="min-w-0 flex-1 truncate text-slate-700 dark:text-slate-200">
                    {r.name}
                  </span>
                  <span className="shrink-0 font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                    {r.agents}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </ChartCard>

        <ChartCard title="Lowest scoring agents" subtitle="Where to start">
          {b.worst_agents.length === 0 ? (
            <p className="text-sm text-slate-400">Nothing scored.</p>
          ) : (
            <ul className="space-y-3">
              {b.worst_agents.map((a) => (
                <li key={`${a.bot_id}-${a.scan_id}`} className="flex items-center gap-3 text-sm">
                  <span
                    aria-hidden
                    className="inline-grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold text-white"
                    style={{ background: gradeColor(a.grade) }}
                  >
                    {a.grade}
                  </span>
                  <span className="sr-only">Grade {a.grade}</span>
                  {a.bot_id ? (
                    <Link
                      to={`/agents/${encodeURIComponent(a.bot_id)}?scan=${a.scan_id}`}
                      className="min-w-0 flex-1 truncate text-brand-600 hover:underline dark:text-brand-400"
                    >
                      {a.agent_name}
                    </Link>
                  ) : (
                    <span className="min-w-0 flex-1 truncate">{a.agent_name}</span>
                  )}
                  <span className="shrink-0 font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                    {a.score}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </ChartCard>
      </div>

      <ListCard title="Suggested actions" tone="neutral" items={actions} empty="" numbered />
    </div>
  );
}

/** "up 4 points on last period" / "unchanged" / "" when there is no baseline. */
function deltaHint(d: number | null, noun: string): string {
  if (d === null) return "No previous period";
  if (d === 0) return "Unchanged on last period";
  const word = d > 0 ? "up" : "down";
  const n = Math.abs(d);
  return `${word} ${n} ${noun}${n === 1 ? "" : "s"} on last period`;
}

function Header({ period, generatedAt }: { period: string; generatedAt: string }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
          Executive briefing
        </h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {period ? `${period} · ` : ""}Prepared {generatedAt}
        </p>
      </div>
    </div>
  );
}

function GradeMix({ period }: { period: BriefingPeriod }) {
  const max = Math.max(1, ...GRADES.map((g) => period.grades[g] ?? 0));
  return (
    <div className="card p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
        Grade mix
      </h3>
      <div className="space-y-2">
        {GRADES.map((g) => {
          const v = period.grades[g] ?? 0;
          return (
            <div key={g} className="flex items-center gap-3 text-sm">
              {/* The letter is the label. Colour only reinforces it. */}
              <span className="w-4 font-bold text-slate-700 dark:text-slate-200">{g}</span>
              <div className="h-4 flex-1 rounded bg-slate-200 dark:bg-slate-700">
                <div
                  className="h-4 rounded"
                  style={{ width: `${(v / max) * 100}%`, background: gradeColor(g) }}
                />
              </div>
              <span className="w-6 text-right font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                {v}
              </span>
            </div>
          );
        })}
      </div>
      <h3 className="mb-3 mt-6 text-sm font-semibold text-slate-700 dark:text-slate-200">
        Open findings
      </h3>
      <ul className="space-y-1.5 text-sm">
        {SEVERITIES.map((s) => (
          <li key={s} className="flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ background: sevColor(s) }}
            />
            <span className="capitalize text-slate-500 dark:text-slate-400">{s}</span>
            <span className="ml-auto font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              {period.findings_by_severity[s] ?? 0}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Severity as a coloured dot *and* its word — never the colour alone. */
function SeverityTag({ severity }: { severity: string }) {
  return (
    <span className="inline-flex w-20 shrink-0 items-center gap-1.5 text-xs font-medium capitalize text-slate-500 dark:text-slate-400">
      <span
        aria-hidden
        className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
        style={{ background: sevColor(severity) }}
      />
      {severity}
    </span>
  );
}

function ListCard({
  title,
  tone,
  items,
  empty,
  numbered = false,
}: {
  title: string;
  tone: Tone;
  items: string[];
  empty: string;
  numbered?: boolean;
}) {
  return (
    <div className="card p-6">
      <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
        <span aria-hidden className={`text-xs ${toneClass(tone)}`}>
          {toneMark(tone)}
        </span>
        {title}
      </h3>
      {items.length === 0 ? (
        <p className="text-sm text-slate-400">{empty}</p>
      ) : (
        <ol className="space-y-2.5">
          {items.map((t, i) => (
            <li
              key={i}
              className="flex gap-2.5 text-sm leading-relaxed text-slate-600 dark:text-slate-300"
            >
              <span className="shrink-0 text-slate-400 dark:text-slate-500">
                {numbered ? `${i + 1}.` : "—"}
              </span>
              <span>{t}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
