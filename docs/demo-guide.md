# Demo guide — Copilot Studio Agent Quality Reporter

**For a stand-in presenter at the Avanade booth, 6DAI Sydney, Thursday 15 October 2026.**
You do not need to know this product. Read section 2, then follow section 3 in order.

---

## 1. The 60-second pitch

Copilot Studio made it easy for anyone in your business to build an agent. Which means that
right now, across your environments, you have some number of agents in production that nobody
has reviewed, built by people who are not developers, and you cannot tell the good ones from
the embarrassing ones without opening each one by hand.

This scores every agent you have, in every environment, against a catalogue of standards — does
it live in a proper solution rather than the default one, does it have a real description, are
its instructions substantial enough to work, does it use connection references instead of
hardcoded connections, is it on a supported model. Every agent comes out with a score out of a
hundred and a letter grade, every failure comes with a plain explanation of what to fix, and
the whole catalogue is editable, so if you disagree with a rule you turn it off or change what
it is worth. Optionally it will also have a model read each agent's instructions and judge how
clearly they are written.

Then it does the thing a one-off audit cannot: it keeps scanning, so you watch the score move
as people fix things. And it tells you *who* is building agents, so you know who needs help —
which, in most organisations, is about a dozen people nobody has met.

Like the rest of the suite, it is self-hosted: one button into your own Azure subscription, a
small managed database and two small containers, no Power BI and no Power Platform reporting
layer. Free, open source, MIT licence, no Microsoft support agreement.

It is for whoever is going to be asked, at some point, to sign off that these agents are fit
for production.

---

## 2. Before you start

**Credentials.** Username `admin`. The password is in the private
`Copilot-Reporting-Demos` repo on Gitea, at `docs/demo-credentials.md` —
<https://gitea.strant.casa/loryanstrant/Copilot-Reporting-Demos>. It is
deliberately not written here: this repository is mirrored to public GitHub.
It is also in Vaultwarden (org **Strant Family**, collection **LS Development**).


**● Open this five minutes before you need it.** The demo instance is set to sleep when nobody
is using it, so the **first page load takes 30 to 60 seconds** and looks like a hung browser.
Once it is awake it stays quick. When this was last checked on 1 October 2026 a cold start took
30 seconds — the slowest of the four. Load it, leave the tab open, and do not close it between
visitors.

- **URL:** https://agentqa-api-yvh7pz3d.politeplant-68b9b614.australiaeast.azurecontainerapps.io
- **Also linked from:** https://copilotreports.strant.com — the landing page with all four
  products as cards. It is being set up now and the name may still be propagating, so use the
  long URL above as your reliable route in.
- **Username:** `admin`
- **Password:** in Vaultwarden, item **"Copilot demo AZURE — Copilot Studio Agent Quality
  Reporter admin"** (organisation *Strant Family*, collection *LS Development*).

Have the password open on your phone before the conference starts. Do not write it anywhere.

---

## 3. The click path

The left sidebar is grouped into **You**, **Organisation**, **Administration** and **Help**.
All the figures below were read off the live demo instance on 1 October 2026. If a number on
screen differs, say the number on screen — it is the real one.

**You land on "Your agents", not the dashboard.** The demo binds the admin login to one of the
fictional agent builders, so the first page is that person's own agents.

### 1. Your agents (`/`)

Point at the score-per-scan bars with the trend line, and at **How you compare**.

> "This is what each of your agent builders sees — their own agents, their own score, and how
> they compare with everyone else building agents. The comparison is withheld entirely if the
> group is too small to show without identifying somebody, and the page says so rather than
> just going blank."

**Say out loud: 20 agents, averaging 89 out of 100, with 59 things still open.**

### 2. Overview (`/org`)

Leave the environment selector on **All environments**. Every agent in the tenant, worst score
first, each row showing its solution, whether it is published, a score bar and a letter grade.

> "Every agent you have, across every environment, ranked. This is the list that does not exist
> anywhere in Copilot Studio."

**Say out loud: 120 agents across three environments.** Then: "How many agents do you think you
have? Most people are wrong by a factor of two."

### 3. Briefing (`/briefing`)

Scroll it.

> "The whole tenant in a few sentences, this period against the last — and again, there's no
> model anywhere in this page. Every number is a database query and every sentence is built
> from fixed rules, because this gets read out to people who will hold you to it."

**Say out loud: the average score went from 74 to 86, and open findings halved — 345 down to
194.** Then the important half of that sentence:

> "And that's the whole argument for this being a report rather than an audit. An audit tells
> you it's bad once. This tells you it's getting better, every week, with a number."

Point at the blocker count — **36 blockers** — and note the severities are words, not colours.

### 4. Agent creators (`/creators`)

Listed alphabetically by name, with their department, their manager, how many agents they have
built and what those agents average. Click a name and the table filters to just their agents.

> "This is the one people don't expect. Fourteen people in this fictional company have built an
> agent. In a real tenant it's usually a handful you've never met, in a department you weren't
> expecting. Now you know who to go and help."

**Say out loud: one person here has built 15 of the 120 agents.** That is Omar Haddad in the
demo data, averaging 81 out of 100 across three environments.

Mention, because it is a nice detail: a builder the directory lookup cannot resolve — somebody
who has left, or an automated account — is kept and listed by their sign-in address rather than
being quietly dropped along with their agents.

### 5. An agent scorecard (click any agent name)

The score gauge, the metadata, every finding with its explanation, and links straight into
Copilot Studio and the maker portal to go and fix it.

> "Every failure tells you what to change and why it matters. And it links straight into
> Copilot Studio — the person who has to fix it is one click away from the thing they need to
> fix."

### 6. Rules (`/rules`)

Under **Administration**. Every rule, editable.

> "And if you disagree with a rule — turn it off, or change what it's worth. These are your
> standards, not somebody else's. That's usually the question that decides whether a platform
> team will actually adopt a tool like this."

### 7. History (`/history`)

Average score over time with the best-to-worst spread shaded behind the line, and the biggest
movers since each agent was last measured — direction shown as ▲ ▼ and the words up and down.

> "Direction and spread together. An average that's climbing while one agent falls apart looks
> like progress on a plain line, and looks like trouble as soon as you can see the band."

---

## 4. Three questions executives will ask

**"Where does our data go?"**
Into your own Azure subscription and nowhere else. It reads your agents live from your own
Power Platform environments and writes to your own database. If you switch on the optional
instruction-quality judge, the agent's instruction text goes to **your own** Azure OpenAI
deployment — still your subscription, still no third party. Turn the judge off and literally
nothing leaves your tenant; the rule-based scoring, which is most of the value, works without
it.

**"Do we need Power BI, Fabric or the Power Platform licences for this?"**
You need Power Platform environments, obviously — that is where the agents live. But you need
no Power BI licence, no Fabric capacity, and no Power Platform reporting layer: this is one
container and one database, and the dashboard is part of the application. It reads your
environments; it does not deploy anything into them.

**"How long to deploy, and who supports it?"**
The deployment is one button and about fifteen minutes. The real work — and be honest about
this, because it is the thing that bites — is that the account it reads with has to be
registered in **every** Power Platform environment you want scanned, one at a time. One app
registration, but one registration step per environment, done by a Power Platform
administrator. There is a scripted command for it and it takes a minute per environment, but if
you have forty environments, that is forty steps. On support: free, open source, MIT licence,
community project. No Microsoft support agreement and no service level agreement.

---

## 5. If it breaks

**◐ Cold start — the normal case.** The page sits blank or spinning for up to a minute, then
loads completely and is quick from then on. This is the slowest of the four to wake. Say,
honestly:

> "These demos are set to sleep when nobody's on them, so it's just waking up — give it thirty
> seconds. In your own tenant it would be running all the time."

Then keep talking. Do not refresh repeatedly; it does not help.

**○ Genuinely down — rare.** You waited a full two minutes, refreshed twice, and you are
getting an error page or a connection failure rather than a slow load. Do not debug at the
booth:

> "The live one's not cooperating — let me show you the actual screens instead, they're the
> same thing."

**The fallback, in this repo:**

- **Screenshots:** `docs/screenshots/` — `overview.png`, `briefing.png`, `creators.png`,
  `agent-detail.png`, `personal.png`, `rules.png`, `history.png`, `scan-history.png`,
  `admin.png`, `setup-guide.png`, `about.png`, `login.png`, and a dark-mode version of every
  one. Walk these in the same order as section 3.
- **Video:** the 30-second video for this product belongs at
  `docs/videos/Copilot Studio Agent Quality Reporter - 30s.mp4`. **As of 1 October 2026 it is
  not yet committed** — check the folder before the event, and if it is empty, the screenshots
  are your fallback.

Have the screenshots open in a second browser tab before the doors open.

---

## 6. What NOT to promise

- **The account it reads with must be registered in every single Power Platform environment
  you want scanned.** This is the real limit of this product and the thing a stand-in most
  often gets wrong. It is one app registration, but it has to be added as an application user
  *per environment*, by a Power Platform administrator. An environment nobody registered it in
  is simply not scanned — and a scan that comes back with no agents almost always means exactly
  that. Never say "point it at your tenant and it finds everything".
- **Application Insights cannot be checked automatically.** Copilot Studio stores that
  connection outside the place this product can read, so that one rule is always flagged for a
  human to review and never counts as a failure. Say so if someone asks why it is always
  amber-with-a-word rather than pass or fail.
- **The instruction-quality judge is optional and needs your own Azure OpenAI.** The demo you
  are showing has **no Azure OpenAI resource behind it** — the judge results in it are
  pre-computed. Rule-based scoring is the part that works out of the box.
- **It scores agents, not people.** Creator names are there so you know who to help. If anyone
  in a government or union-sensitive organisation hears "performance management", correct it
  immediately — that is not what this is and the product documentation says so explicitly.
- **It is a desktop dashboard.** No phone layout, none planned.
- **There is no support contract.** MIT licence, community project, no service level agreement,
  no Microsoft backing.
- **Do not quote a dollar figure for running it.** Describe the shape and let their team price
  it.

---

## 7. Everything on screen is fake

Say this before anybody has to ask:

> "Just so you know up front — everything you're about to see is invented. It's a fictional
> company called Avanoso, with made-up agents and made-up people building them. There's no real
> tenant connected to this and never has been."

Every agent name, environment, score, finding and builder is synthetic data created by a
seeding script in this repository. There are no real people, no real agents and no real
organisation anywhere in it. Saying so unprompted is what makes the rest of what you say
credible — and this room is full of people whose job is to worry about exactly that.

---

## Shutting the demo down after the event

The four demos live in the **MVP 1k** Azure subscription, in four resource groups:
`rg-copilot-usage-demo`, `rg-copilot-prompts-demo`, `rg-copilot-agents-demo`,
`rg-copilot-cowork-demo`, plus `rg-copilot-demos-site` for the landing page.

The container apps are already set to `minReplicas: 0`, so they cost nothing while
nobody is looking at them. **The Postgres flexible servers are not** — they bill
whether or not anyone visits.

◐ **Stopping a Postgres flexible server is not permanent.** Azure automatically
starts a stopped server again after **7 days**. If you stop them and forget, they
quietly resume billing a week later.

● **The durable option is to delete the resource groups** once the event is over.
Everything is reproducible — each repo ships its own one-click template, so standing
the demo back up later is a template deployment and a `seed-demo` call, not a rebuild.

Ask Loryan before deleting anything: the same subscription hosts unrelated work.
