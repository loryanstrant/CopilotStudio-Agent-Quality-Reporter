import { useState } from "react";
import { APP_DISPLAY_NAME, DATAVERSE_TABLES, ENTRA_SCRIPT, PAC_SCRIPT } from "../lib/setup";

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard blocked — user can select manually */
        }
      }}
      className="shrink-0 rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}

export default function SetupGuidePage() {
  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Setup guide</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Everything needed to connect the reporter to your Power Platform environments,
          and what to check when something looks wrong.
        </p>
      </div>

      <div className="card p-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Before you start
        </h3>
        <ul className="list-inside list-disc space-y-1.5 text-sm text-slate-600 dark:text-slate-300">
          <li>
            A <span className="font-medium">Power Platform Administrator</span> to register
            an application user in each environment you want to scan.
          </li>
          <li>
            A <span className="font-medium">Global Administrator</span> (or Application
            Administrator) if you want the optional Entra group gate on viewer sign-in.
          </li>
          <li>
            Optionally an <span className="font-medium">Azure OpenAI</span> deployment, if
            you want the LLM instruction-quality judge. Rule-based scoring works without it.
          </li>
          <li>PowerShell 7 with the Microsoft Graph SDK, or the Power Platform CLI.</li>
        </ul>
      </div>

      <div className="card p-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          How access works
        </h3>
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          The reporter reads agents <span className="font-medium">live from the Dataverse
          Web API</span> using a service principal. That is granted per environment by
          registering the app as an <span className="font-medium">application user</span> —
          it is not a Graph permission. It needs read access to these tables:
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {DATAVERSE_TABLES.map((t) => (
            <div
              key={t}
              className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-900"
            >
              <code className="text-xs text-slate-700 dark:text-slate-200">{t}</code>
              <CopyButton text={t} />
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
          <span className="font-medium">Directory.Read.All</span> on Microsoft Graph is only
          needed if you restrict dashboard viewers to an Entra security group.
        </p>
      </div>

      <div className="card p-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Part A — create the app registration
          </h3>
          <CopyButton text={ENTRA_SCRIPT} label="Copy script" />
        </div>
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
          Creates the registration named{" "}
          <span className="font-medium">{APP_DISPLAY_NAME}</span>, grants consent for the
          optional Graph permission, creates a client secret, and prints the three values to
          paste into Settings.
        </p>
        <pre className="max-h-96 overflow-auto rounded-md bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
          <code>{ENTRA_SCRIPT}</code>
        </pre>
      </div>

      <div className="card p-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Part B — register it in each environment
          </h3>
          <CopyButton text={PAC_SCRIPT} label="Copy script" />
        </div>
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
          Run once per environment you want to scan. You can also do this in the Power
          Platform admin centre under{" "}
          <span className="font-medium">Environment → Settings → Users + permissions →
          Application users → New app user</span>.
        </p>
        <pre className="max-h-96 overflow-auto rounded-md bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
          <code>{PAC_SCRIPT}</code>
        </pre>
      </div>

      <div className="card p-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Troubleshooting
        </h3>
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="font-medium text-slate-800 dark:text-slate-100">
              Test succeeds but an environment returns no agents
            </dt>
            <dd className="text-slate-600 dark:text-slate-300">
              The application user isn't registered in that specific environment, or its
              security role has no read access to the Bot table. Part B is per environment.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-800 dark:text-slate-100">
              401 or 403 from Dataverse
            </dt>
            <dd className="text-slate-600 dark:text-slate-300">
              Check the environment URL is the org URL (for example
              <code className="mx-1">https://contoso.crm6.dynamics.com</code>) and that the
              client secret hasn't expired.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-800 dark:text-slate-100">
              The LLM judge never runs
            </dt>
            <dd className="text-slate-600 dark:text-slate-300">
              It's optional and off until Azure OpenAI is configured in Settings. Rule-based
              scoring runs regardless; judge findings simply won't appear.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-800 dark:text-slate-100">
              Application Insights always shows as manual review
            </dt>
            <dd className="text-slate-600 dark:text-slate-300">
              By design. Copilot Studio stores that connection outside Dataverse, so a
              service-principal scan can't confirm it either way.
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
