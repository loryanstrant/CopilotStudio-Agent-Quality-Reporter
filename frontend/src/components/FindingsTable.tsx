import { Finding, cleanPP } from "../api/types";

const STATUS_STYLE: Record<string, string> = {
  pass: "badge badge-pass",
  fail: "badge badge-fail",
  skipped: "badge badge-skip",
};
const SEV_STYLE: Record<string, string> = {
  blocker: "badge badge-blocker",
  major: "badge badge-major",
  minor: "badge badge-minor",
  info: "badge badge-info",
};

export default function FindingsTable({ findings }: { findings: Finding[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
            <th className="py-2 pr-3 font-medium">Rule</th>
            <th className="py-2 pr-3 font-medium">Check</th>
            <th className="py-2 pr-3 font-medium">Status</th>
            <th className="py-2 pr-3 font-medium">Severity</th>
            <th className="py-2 pr-3 font-medium">Level</th>
            <th className="py-2 pr-3 font-medium">Explanation</th>
            <th className="py-2 pr-3 font-medium">P&amp;P Reference</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f, i) => (
            <tr key={i} className="border-b border-slate-200 dark:border-slate-700 align-top">
              <td className="py-2 pr-3 font-mono text-xs leading-5 text-slate-500 dark:text-slate-400 whitespace-nowrap">{f.rule_id}</td>
              <td className="py-2 pr-3 text-slate-900 dark:text-slate-100">{f.name}</td>
              <td className="py-2 pr-3">
                <span className={STATUS_STYLE[f.status] || "badge badge-off"}>
                  {f.status}
                  {f.manual_review ? " · manual" : ""}
                </span>
              </td>
              <td className="py-2 pr-3">
                <span className={SEV_STYLE[f.severity] || "badge badge-off"}>{f.severity}</span>
              </td>
              <td className="py-2 pr-3 text-slate-500 dark:text-slate-400 whitespace-nowrap">
                {f.scope.startsWith("bot:") ? "agent" : "solution"}
              </td>
              <td className="py-2 pr-3 text-slate-500 dark:text-slate-400 max-w-md">{f.details}</td>
              <td className="py-2 pr-3 text-slate-500 dark:text-slate-400 text-xs whitespace-nowrap">{cleanPP(f.pp_reference)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
