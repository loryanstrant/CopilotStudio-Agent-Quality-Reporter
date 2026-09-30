import { Link } from "react-router-dom";
import { gradeColor } from "./chartTheme";
import type { Mover } from "../api/types";

/**
 * What moved most since each agent was last measured.
 *
 * Every row reads in greyscale: an arrow **and** the word up/down, the two
 * scores, the signed difference, and both grades as letters. Colour reinforces
 * the letter and carries nothing on its own — the owner of this app is
 * colour-blind, and a red-versus-green movers list would be the single worst
 * place in the product to forget that.
 */
export default function MoversList({ movers }: { movers: Mover[] }) {
  if (movers.length === 0) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No agent's score changed between the last two scans in this selection.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-slate-200 text-sm dark:divide-slate-700">
      {movers.map((m) => {
        const up = m.direction === "up";
        return (
          <li key={m.bot_id} className="flex items-center gap-3 py-2">
            <span
              className={`w-24 shrink-0 font-semibold tabular-nums ${
                up
                  ? "text-emerald-700 dark:text-emerald-400"
                  : "text-rose-700 dark:text-rose-400"
              }`}
            >
              <span aria-hidden>{up ? "▲" : "▼"}</span>{" "}
              {up ? "+" : ""}
              {m.delta}
            </span>
            <span className="min-w-0 flex-1 truncate text-slate-900 dark:text-slate-100">
              <Link to={`/agents/${m.bot_id}`} className="hover:underline">
                {m.agent_name}
              </Link>
            </span>
            <span className="shrink-0 text-xs text-slate-500 dark:text-slate-400">
              {/* The word, so the arrow is never the only signal. */}
              {up ? "up" : "down"} from {m.from_score} to {m.to_score}
            </span>
            <span className="flex shrink-0 items-center gap-1">
              <GradeChip grade={m.from_grade} />
              <span aria-hidden className="text-slate-400">
                →
              </span>
              <GradeChip grade={m.to_grade} />
              <span className="sr-only">
                grade {m.from_grade} to grade {m.to_grade}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function GradeChip({ grade }: { grade: string }) {
  return (
    <span
      aria-hidden
      className="inline-grid h-5 w-5 place-items-center rounded text-[11px] font-bold text-white"
      style={{ background: gradeColor(grade) }}
    >
      {grade}
    </span>
  );
}
