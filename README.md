# Copilot Studio Agent Quality Reporter

Self-hosted quality scoring for your **Microsoft Copilot Studio agents**. It reads agents live
from the Dataverse Web API, applies a weighted, editable catalogue of patterns and practices plus
an optional LLM instruction-quality judge, and serves per-agent scorecards, findings and history
across every Power Platform environment — instead of a static report. No data leaves your
subscription. Runs anywhere with `docker compose up`, or deploys to Azure Container Apps in one
click.

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Floryanstrant%2FAgentQualityReporter%2Fmain%2Finfra%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Floryanstrant%2FAgentQualityReporter%2Fmain%2Finfra%2FcreateUiDefinition.json)

> Community project, MIT-licensed. Not covered by a Microsoft support agreement.
## Screenshots

### Overview — every agent, every environment

Pick an environment from the selector, or leave it on **All environments** to see every agent across your tenant, sorted by score. Each row shows the owning solution (display name), publish state, score bar, and grade.

![Overview](docs/screenshots/overview.png)

### Agent scorecard

A full breakdown for one agent: score gauge, metadata (created/modified, human creator, model, environment), deep links straight into **Copilot Studio** and the **maker portal**, every rule finding with its explanation and patterns-&-practices reference, live telemetry (when App Insights is connected), and the LLM instruction-quality judge.

![Agent detail](docs/screenshots/agent-detail.png)

### Settings

Password-protected console: manage environments (add, **edit**, test, scan, delete), scan all environments at once, configure the Dataverse service principal and LLM judge, and open the editable rules catalogue. The version/build stamp and a guided setup wizard live here too.

![Admin](docs/screenshots/admin.png)

### About

App version/build, a plain-English explainer of how scoring works, and credits with links.

![About](docs/screenshots/about.png)

### Dark mode

Every page supports a light and dark theme.

![Overview in dark mode](docs/screenshots/overview-dark.png)


## Deploy to Azure (one click)

The button provisions everything into a resource group of your choice: a PostgreSQL flexible
server, a Container Apps environment, and the **api** + **worker** container apps (pulled as
prebuilt public images from GitHub Container Registry). You only enter an **admin password** — the
database password and encryption keys are generated for you. When the deployment finishes, open the
`dashboardUrl` output, sign in, and complete the in-app **Settings** page to connect your Dataverse
service principal.

To deploy from source with `azd` instead, see [`docs/deploy.md`](docs/deploy.md).

## After it's deployed

**1. Open the dashboard.** In the portal, go to your resource group → open the deployment (or
Deployments → the `Microsoft.Template` run) → **Outputs** → copy **`dashboardUrl`**. That is your app.
It's served by the **`…-api-…`** Container App (the `…-worker-…` one has no web UI — it just runs
scheduled scanning in the background). You can also get the URL from the api Container App's
**Overview → Application Url**.

**2. Sign in.** Username is what you set as **admin username** (default `admin`); password is the
**admin password** you chose at deploy time. The admin console is always password-protected.

**3. Connect your Dataverse service principal.** Go to **Settings**. The setup guide walks you through
creating one Entra **app registration** with the **Dynamics CRM `user_impersonation`** application
permission, then registering it as an **application user** (with a role that can read bots, bot
components, and solutions) in each environment you scan. Paste **Tenant ID**, **Client ID**, and
**Client secret**. Optionally add an **Azure OpenAI / Foundry** base URL, model, and key to enable
the LLM instruction-quality judge.

**4. Add environments and scan.** On **Settings**, **Add environment** → paste its Dataverse org URL
(e.g. `https://org.crm.dynamics.com`) → **Test** → **Run now** (or **Run all environments**). The
environment card shows the last-scan time and agent count; the Overview page shows live scan
progress. You can **Edit** an environment later to rename it or add Application Insights details.

### Restrictions and things to know

- **Application Insights (AGT-007)** can't be read by a service principal — Copilot Studio stores its
  connection outside Dataverse and its bot-management API rejects app-only tokens. This rule is
  therefore **manual-review** and never fails on absence. Connecting an environment's App Insights in
  Admin lets telemetry be confirmed automatically instead.
- **A scan that finds no agents** usually means the app registration isn't registered as an
  **application user** in that environment, or its security role can't read `bot` rows. Re-check the
  setup guide's step 2 and use **Test** on the environment.
- **The service principal needs per-environment access** — one app registration, added as an
  application user in *each* environment you want to scan.

### Enabling Entra ID single sign-on (optional)

By default the dashboard is protected by the single admin password. You can additionally let
colleagues sign in with their **work account** (read-only viewer) — administration stays behind
the password.

Sign-in is performed by the app itself, so it works the same wherever you run it: Azure, Docker
on a NAS, Kubernetes, anywhere. There is nothing to configure on the hosting platform.

It reuses the **same app registration** you already entered for scanning, so there is no second
set of credentials to manage:

1. Sign in as the admin and open **Settings**.
2. Copy the **redirect URI** shown under *Sign in with Microsoft (optional)*.
3. In the Entra portal, open your app registration → **Authentication → Add a platform → Web**,
   and paste that redirect URI.
4. Optionally set a **report access group ID** in Settings to restrict who can view the dashboard.
   If you do, add a **groups** claim under **Token configuration** on the app registration.

The sign-in page then shows a **"Sign in with Microsoft"** button.

> **Behind a reverse proxy?** The app works out its own public address from the request. If your
> proxy doesn't pass the standard forwarded headers, set `PUBLIC_BASE_URL` (for example
> `https://aqp.contoso.com`) so the redirect URI is correct.

Full details: [`docs/deploy.md`](docs/deploy.md#entra-single-sign-on-optional).

### Where to find run history, logs, and errors

- **In the app:** the **Overview** page shows live scan progress; **History** shows past scans with
  scores; each environment card on **Settings** shows its last-scan time and agent count.
- **Container logs (the real detail):** manual **Run now** / **Scan all** run inside the
  **`…-api-…`** Container App — open it → **Monitoring → Log stream** (live), or **Logs** to query
  `ContainerAppConsoleLogs_CL`. Scheduled background scans run in the **`…-worker-…`** Container App —
  check its log stream for scheduled-run errors.


## What it scores

Findings come from a **rule catalogue** ([`engine/rules/rule-catalogue.md`](engine/rules/rule-catalogue.md)) that maps each rule back to a patterns & practices reference. Rules are grouped into:

- **Solution hygiene** — the agent lives in a custom solution (not the default), a custom publisher prefix, a non-default version, connection references instead of hardcoded connections, and environment variables for env-specific values.
- **Agent configuration** — display name, meaningful description, substantive (but not excessive) instructions, user-created or customised topics, suggested prompts, Application Insights, a GA/default model, and a custom icon.
- **Instruction quality (LLM judge, optional)** — clarity, persona, scope discipline, orchestrator/child patterns, and output-format guidance, scored by an Azure OpenAI / Foundry model against the instructions.

Every rule is **editable** from the Rules page: enable/disable it, change its scoring weight, or reword its explanation. Scores are `100 − Σ(weights of failed rules)`, graded A ≥ 90, B ≥ 75, C ≥ 60, D ≥ 40, F below.

> **Application Insights (AGT-007):** Copilot Studio stores the App Insights connection outside Dataverse, and its bot-management API rejects app-only tokens, so a service-principal scan can't read it. This rule is therefore **manual-review** — it never fails on absence. Connect an environment's App Insights in Admin and telemetry is confirmed automatically.

## Prerequisites & permissions

- A **Power Platform Administrator** to register an application user in each environment you want
  to scan.
- A **Global Administrator** (or Application Administrator) only if you want the optional Entra
  group gate on viewer sign-in.
- Optionally an **Azure OpenAI** deployment for the LLM instruction-quality judge. Rule-based
  scoring works without it.
- PowerShell 7 with the Microsoft Graph SDK, or the Power Platform CLI.

Agents are read **live from the Dataverse Web API** using a service principal. That access is
granted per environment by registering the app as an **application user** — it is not a Graph
permission. It needs read access to these tables:

| Table | Why |
| --- | --- |
| Bot | The agents themselves — name, description, instructions, publish state. |
| Bot Component | Topics, knowledge sources and other components used for scoring. |
| Connection Reference | Detects connections used by the agent. |
| Environment Variable Definition | Detects configuration handling. |
| Solution | Solution hygiene rules (managed/unmanaged, publisher prefix). |

Directory.Read.All on Microsoft Graph is needed **only** if you restrict dashboard viewers to an
Entra security group.

Setup is two parts, both scripted. The in-app **Setup guide** page and the Settings wizard carry
copy-paste scripts for each:

**Part A — create the app registration** (Microsoft Graph PowerShell). Creates the registration,
grants consent for the optional Graph permission, creates a client secret, and prints the Tenant ID,
Client ID and secret.

**Part B — register it per environment** (Power Platform CLI):

```powershell
# Power Platform CLI (pac). Install: https://aka.ms/PowerPlatformCLI
# Run once per environment you want to scan. Requires Power Platform admin rights.
pac auth create
pac admin list                 # copy the Environment ID you want to scan

pac admin create-service-principal \
  --environment <ENVIRONMENT-ID> \
  --role "System Administrator"

# Prints: Application (client) ID, Tenant ID, and Client secret.
# 'System Administrator' is convenient for a lab; scope to a least-privilege
# custom role (read on the tables listed above) for production.
```

You can do Part B in the Power Platform admin centre instead, under **Environment → Settings →
Users + permissions → Application users → New app user**.

## Quick start (local)

```powershell
# 1. Create your env file and a Fernet key
Copy-Item .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste the printed value into FERNET_KEY in .env

# 2. Start the production stack (api + worker + postgres)
docker compose up -d
```

- **Dashboard + API:** http://localhost:8002
- **API + Swagger docs:** http://localhost:8002/docs
- **API health check:** http://localhost:8002/health
- **Postgres:** localhost:5434 (user/pass/db all `agentquality` by default)

This is the production stack: it runs prebuilt images with no bind mounts and no
auto-reload, and the API serves the built dashboard itself — so there is no separate
frontend container or web port. `docker compose up` pulls the published images; add
`--build` to build them locally instead.

Every solution in the suite owns a distinct port block, so all four can run side by
side without clashing:

| Solution | API / dashboard | Postgres |
|---|---|---|
| M365 Copilot Usage Reporter | 8000 | 5432 |
| M365 Copilot Cowork Reporter | 8001 | 5433 |
| **Copilot Studio Agent Quality Reporter** | **8002** | **5434** |
| M365 Copilot Prompt Analyser | 8003 | 5435 |

Override `API_PORT` / `DB_PORT` in `.env` to move them. Only the host side changes —
container-internal wiring is unaffected.

### Developing against it

For hot-reload while working on the code, layer the dev override on top. It builds
locally, bind-mounts the source, enables `uvicorn --reload` and runs the Vite dev
server:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The dev dashboard is then on http://localhost:5175 (`WEB_PORT`), with the API still
on 8002.

On first start an admin login is seeded from `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`
(defaults `admin` / `change-me` — change these).

## First-run checklist

1. `docker compose up` (or deploy to Azure).
2. Sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` (seeded automatically on first start).
3. **Settings** → follow the guided wizard for Part A, then enter Tenant ID, Client ID and Client
   secret and **Save**.
4. Add each environment (display name + Dataverse org URL), run Part B for it, then **Test**.
5. **Run now** for one environment, or **Run all environments**.
6. Optionally configure Azure OpenAI to enable the LLM judge, and tune weights on **Rules**.

Just evaluating? Skip steps 3–5 and use **Settings → Demo data → Load demo data** instead.

## Authentication

- **Admin console** is always **password-protected** (JWT, seeded admin user).
- **Entra single sign-on (optional)** — the app runs the OpenID Connect sign-in itself, reusing the
  service principal you already configured, so colleagues can view the dashboard with their work
  account on any host. See [docs/deploy.md](docs/deploy.md#entra-single-sign-on-optional).


## Data & privacy notes

- Agent **instructions and descriptions** are read from Dataverse for scoring. If the LLM judge is
  enabled, instruction text is sent to **your own** Azure OpenAI deployment — never to any
  third-party service. Disable the judge and nothing leaves your subscription at all.
- The Dataverse **client secret** and the Azure OpenAI **key** are encrypted at rest with a Fernet
  key and are write-only in the API: they can be set and replaced, never read back.
- Scores are about **agent quality and hygiene**, not the people who built them. Creator names are
  shown so you know who to help, not to rank anyone.
- Application Insights (AGT-007) is always manual-review: Copilot Studio stores that connection
  outside Dataverse, so a service-principal scan cannot confirm it either way.
- Demo data is clearly labelled as such in Settings, and is only ever created or removed by an
  explicit action.

## License

MIT. Community project — no Microsoft support agreement or SLA.
