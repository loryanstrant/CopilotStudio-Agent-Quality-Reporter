// Shared chart styling: a coherent gradient palette + reusable <defs> so every
// Recharts surface gets depth (fills, soft shadows) instead of flat 2D colour.
//
// This file is also the single home of the two *semantic* palettes this app
// needs — grade and severity. They were previously declared as duplicated hex
// literals in five places (api/types.ts, ScoreGauge, SeverityBars, and via
// imports in Overview/Personal/History), which also silently duplicated the
// `pass`/`fail`/`sev-*` tokens in tailwind.config.js. Five copies of a colour
// is four chances for them to drift apart.
//
// Colour is never the only signal in this app: a grade always carries its
// letter and a severity always carries its word. These values decorate a label
// that already reads correctly in greyscale.

export const CHART_COLORS = [
  "#3b6ef5", // brand blue
  "#22c55e", // green
  "#f59e0b", // amber
  "#a855f7", // purple
  "#ef4444", // red
  "#06b6d4", // cyan
  "#ec4899", // pink
  "#14b8a6", // teal
];

// A gradient id for a series index (defs live in <SvgDefs/>, rendered once).
export function gradId(i: number): string {
  return `grad-${i % CHART_COLORS.length}`;
}

export function barGradId(i: number): string {
  return `bargrad-${i % CHART_COLORS.length}`;
}

/** Used for "unknown", "not scored" and "skipped" — matches tailwind `skip`. */
export const NEUTRAL = "#8D99AE";

/** Quality grades, best to worst. Mirrors the tailwind `pass`/`fail` tokens. */
export const GRADE_COLORS: Record<string, string> = {
  A: "#2A9D8F",
  B: "#52B788",
  C: "#E9C46A",
  D: "#F4A261",
  F: "#E63946",
};

/** Finding severities. Mirrors the tailwind `sev-*` tokens. */
export const SEV_COLORS: Record<string, string> = {
  blocker: "#E63946",
  major: "#F4A261",
  minor: "#E9C46A",
  info: "#8AB0AB",
};

export function gradeColor(grade: string | null | undefined): string {
  return (grade && GRADE_COLORS[grade]) || NEUTRAL;
}

export function sevColor(severity: string | null | undefined): string {
  return (severity && SEV_COLORS[severity]) || NEUTRAL;
}

/** The grade a score earns. Mirrors engine/static_rules.py::grade_for_score.
 *
 *  Needed wherever a score is shown without a grade beside it: the band is the
 *  judgement, and a tinted number carries that judgement in hue alone. */
export function gradeForScore(score: number): string {
  if (score >= 90) return "A";
  if (score >= 75) return "B";
  if (score >= 60) return "C";
  if (score >= 40) return "D";
  return "F";
}

/** A 0–100 score, banded onto the same palette the grades use.
 *
 *  The bands match the scorecard's grade boundaries, so a score bar and the
 *  grade badge beside it can never disagree about how the agent is doing. */
export function scoreColor(score: number | null | undefined): string {
  const v = score ?? 0;
  if (v >= 75) return GRADE_COLORS.A;
  if (v >= 60) return GRADE_COLORS.C;
  if (v >= 40) return GRADE_COLORS.D;
  return GRADE_COLORS.F;
}
