# Screenshots

Every image in this folder is produced the same way, from a throwaway local
stack with demo data. Recording it here so the next person does not have to
work it out, and so nobody is tempted to shoot a real tenant.

## The rule that matters

**Never screenshot a deployed instance or a real tenant.** These images end up
in a public README. The stack used here has **no tenant credentials configured
at all**, so it cannot reach Dataverse, Graph or Application Insights even by
accident — the only data in it is the fictional data the seeder writes.

## Producing them

1. Bring up the production stack against a throwaway `.env`. It needs a
   `SECRET_KEY`, a `FERNET_KEY` and an `ADMIN_PASSWORD`, and nothing else —
   leave every tenant field empty.

   ```bash
   cp .env.example .env
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   # paste into FERNET_KEY, set ADMIN_PASSWORD, then:
   docker compose up -d --build
   ```

2. Seed the demo data. This writes fictional environments, agents, scans,
   findings, judge results and telemetry — and points the local admin account
   at one of the seeded agent creators, which is what makes the personal pages
   reachable without an Entra tenant.

   ```bash
   docker compose exec api python -m scripts.seed_demo --agents 18 --reset
   ```

3. Sign in at `http://localhost:8002` with the admin account and take the
   shots. Viewport **1440×900**, which is the width the layout is designed for.

4. Take each one twice: light, then dark via the theme toggle in the sidebar
   footer. Dark versions carry a `-dark` suffix.

## Naming

`<page>.png` and `<page>-dark.png`, lower case, hyphenated:

| File | Page |
|---|---|
| `login` | Sign-in |
| `personal` | Your agents |
| `overview` | Overview |
| `briefing` | Executive briefing |
| `creators` | Agent creators |
| `agent-detail` | One agent's scorecard |
| `history` | Scan history |
| `rules` | Rules catalogue |
| `admin` | Settings |
| `setup-guide` | Setup guide |
| `about` | About |

Every file here should be referenced from the README. An unreferenced
screenshot is a file nobody knows is stale — `login.png` sat here unreferenced
for months before the README gained a "Sign in" section for it.

## What to check before committing one

- No real names, tenant IDs, environment GUIDs or URLs. The seeder's people are
  fictional and its domain is `contoso.local`; if you see anything else, you
  are not looking at demo data.
- The sidebar shows the demo persona, not a real colleague.
- Grades show their letter and severities their word — these images are how
  most people first see the app, and it is built to be readable without
  distinguishing colours.
