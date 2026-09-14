import { useState, type ReactNode } from "react";
import { DATAVERSE_TABLES, ENTRA_SCRIPT, PAC_SCRIPT } from "../lib/setup";


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
      className="shrink-0 rounded-md border border-slate-300 dark:border-slate-600 px-2 py-1 text-xs font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700"
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}

function Chip({ value }: { value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md bg-slate-50 dark:bg-slate-900 px-3 py-2">
      <code className="text-xs text-slate-900 dark:text-slate-100">{value}</code>
      <CopyButton text={value} />
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">
        {n}
      </div>
      <div className="min-w-0 flex-1 space-y-1.5">
        <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h4>
        <div className="text-sm text-slate-500 dark:text-slate-400">{children}</div>
      </div>
    </div>
  );
}

function RoleNote({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
      <span className="shrink-0 rounded bg-brand-600 px-1.5 py-0.5 font-semibold text-white">
        Requires
      </span>
      <span className="leading-relaxed">{children}</span>
    </div>
  );
}

/**
 * Guided setup for the service principal the platform needs to read agents live.
 * Two parts: (A) the Entra app registration, (B) registering that app as an
 * application user in each Power Platform environment. Collapsible.
 */
export default function SetupWizard({ defaultOpen = true }: { defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [showScript, setShowScript] = useState(false);
  const [showEntraScript, setShowEntraScript] = useState(false);

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 bg-slate-50 dark:bg-slate-900 px-6 py-4 text-left"
      >
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Setup guide: service principal for live scanning
          </h2>
          <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
            The platform reads agents live from the Dataverse Web API. Create one Entra app
            registration, then register it as an application user in each environment you scan.
          </p>
        </div>
        <span className="shrink-0 text-slate-500 dark:text-slate-400">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-6 py-5 space-y-8">
          {/* -------- Part A: Entra ID -------- */}
          <div className="space-y-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-500">
              Part A · Microsoft Entra ID (app registration)
            </div>
            <RoleNote>
              Microsoft Entra <span className="font-semibold text-slate-900 dark:text-slate-100">Application Administrator</span>{" "}
              (or Cloud Application Administrator / Global Administrator) — needed to register the app
              and, for the optional <span className="font-mono">Directory.Read.All</span>, to grant
              admin consent. Registering an app alone only needs the{" "}
              <span className="font-semibold text-slate-900 dark:text-slate-100">Application Developer</span> role.
            </RoleNote>

            <Step n={1} title="Create the app registration">
              <p>
                Open{" "}
                <a
                  href="https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/CreateApplicationBlade/quickStartType~/null/isMSAApp~/false"
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-brand-600 dark:text-brand-500 underline"
                >
                  Entra → App registrations → New registration
                </a>
                . Name it something like <span className="font-medium">Copilot Studio Agent Quality Reporter</span>,
                keep the defaults, and select <span className="font-medium">Register</span>.
              </p>
            </Step>

            <Step n={2} title="Create a client secret">
              <p>
                Under <span className="font-medium">Certificates &amp; secrets → New client secret</span>,
                create one and copy its <span className="font-medium">Value</span> immediately — it's
                shown only once.
              </p>
            </Step>

            <Step n={3} title="(Optional) Add a Graph permission for report-group gating">
              <p className="mb-2">
                Only needed if you'll restrict the dashboard to an Entra security group. Under{" "}
                <span className="font-medium">
                  API permissions → Add a permission → Microsoft Graph → Application permissions
                </span>
                , add this and choose <span className="font-medium">Grant admin consent</span>:
              </p>
              <div className="max-w-sm">
                <Chip value="Directory.Read.All" />
              </div>
            </Step>

            <Step n={4} title="Copy the IDs into the form below">
              <p>
                From the app's <span className="font-medium">Overview</span> page, copy the{" "}
                <span className="font-medium">Directory (tenant) ID</span> and{" "}
                <span className="font-medium">Application (client) ID</span>. Paste those plus the
                secret into <span className="font-medium">Service principal &amp; judge</span> below,
                then <span className="font-medium">Save</span>.
              </p>
            </Step>

            <div className="rounded-lg border border-slate-200 dark:border-slate-700">
              <button
                type="button"
                onClick={() => setShowEntraScript((v) => !v)}
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-slate-900 dark:text-slate-100"
              >
                <span>Prefer to script it? Run this instead of steps 1–3</span>
                <span className="text-slate-500 dark:text-slate-400">{showEntraScript ? "▲" : "▼"}</span>
              </button>
              {showEntraScript && (
                <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-3">
                  <div className="mb-2 flex justify-end">
                    <CopyButton text={ENTRA_SCRIPT} label="Copy script" />
                  </div>
                  <pre className="max-h-72 overflow-auto rounded-md bg-brand-600 p-3 text-xs leading-relaxed text-white">
                    <code>{ENTRA_SCRIPT}</code>
                  </pre>
                  <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                    Resolves permission IDs by name, creates the app, (optionally) grants{" "}
                    <span className="font-mono">Directory.Read.All</span> consent, and prints the
                    Tenant ID, Client ID, and secret to paste below.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* -------- Part B: Power Platform -------- */}
          <div className="space-y-5 border-t border-slate-200 dark:border-slate-700 pt-6">
            <div className="text-xs font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-500">
              Part B · Power Platform (application user, per environment)
            </div>
            <RoleNote>
              <span className="font-semibold text-slate-900 dark:text-slate-100">Power Platform Administrator</span> (or a{" "}
              <span className="font-semibold text-slate-900 dark:text-slate-100">System Administrator</span> security role in the
              target environment) — needed to create application users and assign security roles.
              Global / Dynamics 365 Administrator also works.
            </RoleNote>

            <Step n={1} title="Open the environment's application users">
              <p>
                In the{" "}
                <a
                  href="https://admin.powerplatform.microsoft.com/environments"
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-brand-600 dark:text-brand-500 underline"
                >
                  Power Platform admin center
                </a>
                , pick your environment →{" "}
                <span className="font-medium">
                  Settings → Users + permissions → Application users
                </span>{" "}
                → <span className="font-medium">New app user</span>.
              </p>
            </Step>

            <Step n={2} title="Add the app registration">
              <p>
                Choose <span className="font-medium">Add an app</span>, search for the app by its{" "}
                <span className="font-medium">Application (client) ID</span> from Part A, and pick a
                business unit.
              </p>
            </Step>

            <Step n={3} title="Assign a security role with read on the agent tables">
              <p className="mb-2">
                Give the app user a role with <span className="font-medium">Read</span> (Organization
                level) on these Dataverse tables so the scanner can see agents and their config:
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-lg">
                {DATAVERSE_TABLES.map((t) => (
                  <Chip key={t} value={t} />
                ))}
              </div>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Least privilege: a custom role with Organization-level Read on those tables. Quick lab
                option: the built-in <span className="font-medium">System Customizer</span> role.
              </p>
            </Step>

            <Step n={4} title="Repeat per environment, then test">
              <p>
                Do this in every environment you added above. Back here, use{" "}
                <span className="font-medium">Test</span> on the environment, then{" "}
                <span className="font-medium">Run now</span>.
              </p>
            </Step>

            <div className="rounded-lg border border-slate-200 dark:border-slate-700">
              <button
                type="button"
                onClick={() => setShowScript((v) => !v)}
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-slate-900 dark:text-slate-100"
              >
                <span>Prefer to script it? Create the app + app user in one command</span>
                <span className="text-slate-500 dark:text-slate-400">{showScript ? "▲" : "▼"}</span>
              </button>
              {showScript && (
                <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-3">
                  <div className="mb-2 flex justify-end">
                    <CopyButton text={PAC_SCRIPT} label="Copy command" />
                  </div>
                  <pre className="max-h-72 overflow-auto rounded-md bg-brand-600 p-3 text-xs leading-relaxed text-white">
                    <code>{PAC_SCRIPT}</code>
                  </pre>
                  <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                    <span className="font-mono">pac admin create-service-principal</span> creates the
                    Entra app <em>and</em> registers it as an application user in the environment, then
                    prints the Tenant ID, Client ID, and secret to paste below.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* -------- App Insights note -------- */}
          <div className="border-t border-slate-200 dark:border-slate-700 pt-5 text-sm text-slate-500 dark:text-slate-400">
            <span className="font-semibold text-slate-900 dark:text-slate-100">Application Insights (optional):</span> to light
            up live telemetry (runs, errors, latency) per agent, add the environment's App Insights{" "}
            <span className="font-medium">Application ID</span> and an{" "}
            <span className="font-medium">API key</span> (App Insights → API Access) on the environment
            above. No service-principal permission is required for this.
            <span className="block mt-1 text-xs">
              Requires <span className="font-semibold text-slate-900 dark:text-slate-100">Contributor</span> (or Monitoring
              Contributor) on the Application Insights resource to create the API key.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}