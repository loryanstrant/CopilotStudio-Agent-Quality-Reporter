"""Seed synthetic agent-quality data so the dashboards render without Dataverse.

Generates plausible fictional environments, agents, scans, findings and judge
results — no Dataverse or Azure OpenAI calls. Use it to explore the UI locally,
or to demo the reporter before wiring up a tenant.

Run inside the container / venv::

    python -m scripts.seed_demo                   # 3 environments, ~40 agents
    python -m scripts.seed_demo --agents 40 --reset
    python -m scripts.seed_demo --clear

``--reset`` clears the scan/agent tables first. It never touches credentials or
user accounts. It sets exactly one field on ``app_config`` —
``demo_persona_upn`` — so the local admin can reach the personal pages without
an Entra tenant (see :func:`_bind_persona`).
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from scripts._demo_tenant import DOMAIN, ENVIRONMENTS, roster
from shared.db import SessionLocal
from shared.models import (
    Agent,
    AgentCreator,
    AgentScore,
    AppConfig,
    Environment,
    Finding,
    JobRun,
    JudgeResult,
    Scan,
    TelemetrySnapshot,
)
from worker.creators import JOB_NAME as CREATOR_JOB_NAME


def _org_url(display_name: str) -> str:
    """The Dataverse org URL a Power Platform environment of this name would have.

    "Avanoso (default)" -> https://avanoso.crm6.dynamics.com
    "Avanoso — UAT"     -> https://avanoso-uat.crm6.dynamics.com
    """
    slug = display_name.lower().replace(" (default)", "").replace("—", "-")
    slug = "-".join(part for part in slug.replace(" ", "-").split("-") if part)
    return f"https://{slug}.crm6.dynamics.com"


# Environment names come from the shared Avanoso tenant so the suite agrees on
# which fictional organisation it is reporting on.
_ENVIRONMENTS = [(name, _org_url(name)) for name in ENVIRONMENTS]

_AGENT_NAMES = [
    "HR Policy Assistant", "IT Service Desk Bot", "Expense Helper",
    "Onboarding Buddy", "Sales Order Lookup", "Facilities Requests",
    "Benefits Explainer", "Travel Approvals", "Procurement Guide",
    "Payroll FAQ", "Security Awareness Coach", "Contract Summariser",
    "Fleet Booking", "Learning Pathways", "Customer Refunds",
    "Incident Triage", "Vendor Onboarding", "Compliance Checker",
    "Meeting Room Finder", "Asset Tracker",
]

# Agent makers, with a deliberately uneven share of the agents. Every demo
# agent used to be created by one address, a single "demo" service account,
# which made the Agent creators listing a single row and the personal view
# either everything or nothing — neither of which is what either page looks like
# in a real tenant. The weights give a couple of prolific makers, a middle, and
# a long tail.
#
# Only the names and addresses come from the shared Avanoso roster, so the
# makers here are the same employees the sibling solutions report on. Their
# department, office and job title do NOT: those are assigned below from this
# repo's own lists, because the two-department round robin is load-bearing for
# the five-peer disclosure threshold (see ``_maker_department``). Taking the
# roster's own departments would reintroduce the small-team problem that round
# robin exists to solve.
_MAKER_WEIGHTS = [6, 5, 4, 3, 2, 1, 4, 3, 3, 2, 2, 2, 1, 1]
_MAKERS = [
    (person.display_name, person.upn, weight)
    for person, weight in zip(roster(len(_MAKER_WEIGHTS)), _MAKER_WEIGHTS)
]

# Two departments, assigned by **round robin** rather than at random, and
# fourteen makers rather than six. Both numbers are load-bearing.
#
# The team comparison withholds a team below five people other than the viewer
# (a disclosure rule — see docs/specs/comparisons-and-timelines.md). Random
# assignment over a small population produced departments of three, so the
# comparison the demo exists to show never appeared; and a single department
# makes the team average and the organisation average the same number, which
# renders as three identical bars and reads as a bug even though it is correct.
#
# Round-robin over an even count guarantees seven per department: six peers each,
# which clears the threshold with one to spare. The threshold is never lowered to
# make the panel appear.
_DEPARTMENTS = ["Customer Operations", "Finance & Corporate Services"]

# The managers are deliberately **not** makers: in a real tenant the person a
# team reports to usually has not built an agent themselves, so they have no row
# in agent_creators — which is exactly the case the manager fallback has to cope
# with.
_DEPARTMENT_MANAGERS = {
    "Customer Operations": ("mgr-cust-ops", "Dana Whitfield"),
    "Finance & Corporate Services": ("mgr-fin-corp", "Karl Osei"),
}

_OFFICES = ["Melbourne", "Sydney", "Remote — AU"]

_JOB_TITLES = [
    "Business Analyst",
    "Process Lead",
    "Service Designer",
    "Operations Manager",
    "Automation Specialist",
]


def _maker_department(index: int) -> str:
    """Round robin, so every department is the same size by construction."""
    return _DEPARTMENTS[index % len(_DEPARTMENTS)]


# One creator the directory cannot resolve, because that path has to be visible
# in the demo: a service account that built an agent, kept and shown by its UPN
# rather than dropped. Dropping it would take its agent out of every listing.
_UNRESOLVED_MAKER = (
    "svc-agentbuilder",
    f"svc-agentbuilder@{DOMAIN}",
    1,
)

# The maker the local admin account is bound to when demo data is loaded, so
# whoever is evaluating the product lands on a personal view with agents in it.
_DEMO_ADMIN_MAKER = _MAKERS[0]

# Judge prose, one entry per agent slot. Real judge output is a list of short
# points, and these columns are JSON list columns — writing a single string
# here made the agent-detail judge panel render a sentence where the UI expects
# bullets.
_STRENGTHS = [
    ["Clear statement of purpose", "Consistent, professional tone"],
    ["Well-scoped to one business process", "Names its knowledge sources"],
    ["Good escalation wording", "Concise instructions"],
]
_WEAKNESSES = [
    ["No explicit out-of-scope handling", "Persona is implied rather than stated"],
    ["Instructions repeat the topic names", "No guidance on answer length"],
    ["Mixes policy and process in one block"],
]
_CHANGES = [
    ["Add an explicit out-of-scope response", "State the expected output format"],
    ["Split the instructions into purpose, scope and tone", "Name the audience"],
    ["Add a fallback topic that hands off to a human"],
]

_RULES = [
    ("SOL-001", "Agent lives in an unmanaged solution", "solution", "major", 8),
    ("SOL-002", "Default publisher prefix in use", "solution", "minor", 4),
    ("AGT-001", "No description set", "agent", "major", 8),
    ("AGT-002", "Instructions shorter than 200 characters", "agent", "blocker", 15),
    ("AGT-003", "Default icon not replaced", "agent", "minor", 3),
    ("AGT-004", "No topics defined beyond system defaults", "agent", "major", 10),
    ("AGT-005", "Generative answers enabled with no knowledge source", "agent", "blocker", 15),
    ("AGT-006", "No fallback or escalation topic", "agent", "major", 8),
    ("AGT-007", "Application Insights not configured", "agent", "info", 0),
    ("AGT-008", "Authentication set to no authentication", "agent", "major", 10),
]

_GRADE_BANDS = [(90, "A"), (75, "B"), (60, "C"), (40, "D"), (0, "F")]


def _grade(score: int) -> str:
    for threshold, letter in _GRADE_BANDS:
        if score >= threshold:
            return letter
    return "F"


async def _bind_persona(session, upn: str | None) -> None:
    """Point the demo persona at a seeded maker, or clear it.

    Agents are attributed by their creator's UPN, so a password account has no
    "me" to filter a personal view down to and the personal pages are
    unreachable — which meant nobody evaluating this product with demo data
    could see pages the README advertises.

    The binding lives on ``app_config`` beside the rest of the configuration,
    not on the account: it is a property of "this deployment is currently
    showing demo data", not of the person signing in. It is read per request
    (see :func:`api.auth.personal_view_upn`), so clearing the data takes effect
    immediately rather than at the admin's next sign-in.
    """
    cfg = await session.get(AppConfig, 1)
    if cfg is None:
        cfg = AppConfig(id=1)
        session.add(cfg)
    cfg.demo_persona_upn = upn


async def seed(agents: int = 40, reset: bool = True) -> dict[str, int]:
    """Populate the reporting tables with plausible fictional data.

    Returns a stats dict so callers (CLI and the admin endpoint) can report what
    was created.
    """
    rng = random.Random(20260914)
    now = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        if reset:
            # Fact tables only. Credentials and accounts are untouched; the
            # only app_config field written is the demo persona, at the end.
            await session.execute(delete(JobRun))
            await session.execute(delete(AgentCreator))
            await session.execute(delete(TelemetrySnapshot))
            await session.execute(delete(JudgeResult))
            await session.execute(delete(Finding))
            await session.execute(delete(AgentScore))
            await session.execute(delete(Scan))
            await session.execute(delete(Agent))
            await session.execute(delete(Environment))
            await session.flush()

        env_rows: list[Environment] = []
        for name, url in _ENVIRONMENTS:
            env = Environment(
                environment_guid=str(uuid.uuid4()),
                display_name=name,
                dataverse_url=url,
                enabled=True,
                created_at=now,
            )
            session.add(env)
            env_rows.append(env)
        await session.flush()

        names = (_AGENT_NAMES * ((agents // len(_AGENT_NAMES)) + 1))[:agents]
        maker_weights = [w for _, _, w in _MAKERS]
        agent_rows: list[Agent] = []
        for i, agent_name in enumerate(names):
            env = env_rows[i % len(env_rows)]
            # The first agent always belongs to the maker the local admin is
            # bound to, so a freshly seeded demo never opens on an empty
            # personal page however small --agents is.
            if i == 0:
                maker = _DEMO_ADMIN_MAKER
            elif i == 1:
                # Guaranteed, so the "creator we cannot resolve" row always
                # exists however small --agents is.
                maker = _UNRESOLVED_MAKER
            else:
                maker = rng.choices(_MAKERS, weights=maker_weights, k=1)[0]
            maker_name, maker_upn, _ = maker
            agent_rows.append(
                Agent(
                    bot_id=str(uuid.uuid4()),
                    environment_id=env.id,
                    display_name=agent_name,
                    schema_name=f"cr123_{agent_name.lower().replace(' ', '_')}",
                    description=None if rng.random() < 0.3 else f"{agent_name} for staff.",
                    publish_state=rng.choice(["Published", "Published", "Draft"]),
                    created_by_name=maker_name,
                    created_by_upn=maker_upn,
                    created_on=now - timedelta(days=rng.randint(30, 400)),
                    modified_on=now - timedelta(days=rng.randint(0, 30)),
                    last_seen=now,
                )
            )
        session.add_all(agent_rows)
        await session.flush()

        total_findings = 0
        scan_rows: list[Scan] = []

        # One scan per environment per day for the last fortnight, so the
        # history page and the per-agent trend lines have something to draw —
        # then weekly back to eight weeks, so the executive briefing has a
        # *previous* period to compare against. Seeding a fortnight alone left
        # it reporting "no comparable scan in the period before it", which is
        # an honest answer to a question the demo should not be asking.
        day_offsets = sorted(set(range(0, 15)) | set(range(21, 57, 7)), reverse=True)
        for day_offset in day_offsets:
            started = now - timedelta(days=day_offset)
            for env in env_rows:
                env_agents = [a for a in agent_rows if a.environment_id == env.id]
                if not env_agents:
                    continue
                scan = Scan(
                    environment_id=env.id,
                    solution_name="Demo solution",
                    source="demo",
                    # "complete" is the vocabulary the worker writes and every
                    # reader filters on. This said "succeeded", which no query
                    # in the app recognises — so demo data produced an empty
                    # Overview and an empty History, and looked like a product
                    # that does not work.
                    status="complete",
                    started_at=started,
                    finished_at=started + timedelta(minutes=rng.randint(1, 6)),
                    agent_count=len(env_agents),
                    agents_done=len(env_agents),
                    engine_version="demo",
                    catalogue_hash="demo",
                )
                session.add(scan)
                await session.flush()
                scan_rows.append(scan)

                scores: list[int] = []
                for agent in env_agents:
                    score = 100
                    for rule_id, name, scope, severity, weight in _RULES:
                        # Older scans fail more often, so scores trend upward.
                        # Scaled against the full eight-week history: against
                        # the old fortnight it would drive the earliest scans
                        # to near-total failure and flatten every agent to 0.
                        fail_chance = 0.32 * (0.6 + day_offset / 90)
                        failed = rng.random() < fail_chance
                        manual = rule_id == "AGT-007"
                        # "skipped" + manual_review=True is what the engine
                        # actually emits for a rule it cannot score from the
                        # export. The seeder used to invent a "manual" status,
                        # which is not in the schema's vocabulary (pass | fail |
                        # skipped) — so the findings table missed its style and
                        # rendered the badge as "manual · manual".
                        status = "skipped" if manual else ("fail" if failed else "pass")
                        if failed and not manual:
                            score -= weight
                        session.add(
                            Finding(
                                scan_id=scan.id,
                                agent_name=agent.display_name,
                                rule_id=rule_id,
                                name=name,
                                scope=scope,
                                severity=severity,
                                weight=weight,
                                status=status,
                                manual_review=manual,
                                pp_reference="Patterns & Practices",
                                details=f"Demo finding for {agent.display_name}.",
                            )
                        )
                        total_findings += 1

                    score = max(0, min(100, score))
                    scores.append(score)
                    session.add(
                        AgentScore(
                            scan_id=scan.id,
                            bot_id=agent.bot_id,
                            agent_name=agent.display_name,
                            environment_id=env.id,
                            solution_name="Demo solution",
                            publish_state=agent.publish_state,
                            score=score,
                            grade=_grade(score),
                            captured_at=started,
                        )
                    )

                    # Judge results and telemetry only on the most recent scan,
                    # as in a real run.
                    if day_offset == 0:
                        session.add(
                            JudgeResult(
                                scan_id=scan.id,
                                agent_name=agent.display_name,
                                # The judge scores these 0-5 (engine/llm_judge.py)
                                # and the UI renders them out of 5. Seeding 4-10
                                # produced bars reading "8/5" that overflowed
                                # their track.
                                clarity=rng.randint(2, 5),
                                persona_defined=rng.random() < 0.6,
                                scope_discipline=rng.randint(2, 5),
                                output_format_guidance=rng.random() < 0.5,
                                orchestrator_pattern_detected=rng.random() < 0.25,
                                child_pattern_detected=rng.random() < 0.2,
                                summary=(
                                    f"Instructions for {agent.display_name} are workable "
                                    "but could be tighter."
                                ),
                                # Lists, not strings: these are JSON list
                                # columns and the judge panel renders bullets.
                                top_strengths=rng.choice(_STRENGTHS),
                                top_weaknesses=rng.choice(_WEAKNESSES),
                                recommended_changes=rng.choice(_CHANGES),
                                skipped=False,
                            )
                        )

                        # Without this the App Insights panel on every agent
                        # sits empty in demo data, which reads as a broken
                        # feature rather than an unconfigured one. Not every
                        # agent gets one — a tenant where every agent is
                        # instrumented is not a tenant anyone recognises, and
                        # the empty state deserves to be visible too.
                        if rng.random() < 0.75:
                            runs = rng.randint(40, 4000)
                            session.add(
                                TelemetrySnapshot(
                                    scan_id=scan.id,
                                    agent_name=agent.display_name,
                                    window_days=30,
                                    run_count=runs,
                                    error_count=int(runs * rng.uniform(0.0, 0.06)),
                                    p95_latency_ms=round(rng.uniform(400, 4200), 1),
                                    source="demo",
                                    captured_at=started,
                                )
                            )

                avg = round(sum(scores) / len(scores)) if scores else 0
                scan.score = avg
                scan.grade = _grade(avg)

        # A scan that failed, and one that only got part-way. Both states exist
        # in production and neither was reachable in a demo, so nobody had ever
        # seen what Scan history looks like when something goes wrong — which is
        # the state the page exists for.
        broken_at = now - timedelta(days=9, hours=7)
        session.add(
            Scan(
                environment_id=env_rows[-1].id,
                solution_name="Demo solution",
                source="demo",
                trigger="scheduled",
                status="failed",
                started_at=broken_at,
                finished_at=broken_at + timedelta(seconds=41),
                agent_count=0,
                agents_done=0,
                engine_version="demo",
                catalogue_hash="demo",
                detail=(
                    "Dataverse returned 401 Unauthorized. The application user "
                    "may have been removed from this environment."
                ),
            )
        )
        partial_at = now - timedelta(days=4, hours=3)
        session.add(
            Scan(
                environment_id=env_rows[1].id,
                solution_name="Demo solution",
                source="demo",
                trigger="manual",
                status="complete",
                started_at=partial_at,
                finished_at=partial_at + timedelta(minutes=3),
                agent_count=len([a for a in agent_rows if a.environment_id == env_rows[1].id]),
                agents_done=1,
                engine_version="demo",
                catalogue_hash="demo",
                detail="Stopped early: the scan was cancelled from Settings.",
            )
        )

        await _seed_creator_directory(session, now)
        await _seed_job_runs(session, rng, now)

        await _bind_persona(session, _DEMO_ADMIN_MAKER[1])
        await session.commit()

    return {
        "environments": len(_ENVIRONMENTS),
        "agents": len(agent_rows),
        "scans": len(scan_rows),
        "findings": total_findings,
    }


async def _seed_creator_directory(session, now: datetime) -> None:
    """Directory rows for the seeded makers, as a Graph lookup would leave them.

    Demo data never calls Graph — there are no credentials configured and there
    must be no possibility of a tenant call from seeded data — so the rows the
    sync would have written are written here instead. Without them the creators
    listing shows sign-in addresses and the team comparison has no departments
    to group by, which is most of what this release added.
    """
    for index, (name, upn, _weight) in enumerate(_MAKERS):
        department = _maker_department(index)
        manager_id, manager_name = _DEPARTMENT_MANAGERS[department]
        session.add(
            AgentCreator(
                upn=upn.lower(),
                entra_user_id=f"demo-{index:02d}",
                display_name=name,
                department=department,
                job_title=_JOB_TITLES[index % len(_JOB_TITLES)],
                office_location=_OFFICES[index % len(_OFFICES)],
                manager_id=manager_id,
                manager_name=manager_name,
                resolved=True,
                updated_at=now,
            )
        )
    # The one the directory could not resolve. Kept, with the reason, so it shows
    # by UPN wherever creators are listed.
    session.add(
        AgentCreator(
            upn=_UNRESOLVED_MAKER[1].lower(),
            display_name=None,
            resolved=False,
            error="No directory record for this sign-in address.",
            updated_at=now,
        )
    )


async def _seed_job_runs(session, rng: random.Random, now: datetime) -> None:
    """A fortnight of creator-directory runs, including one that failed.

    ``job_runs`` had never been written by this app at all, so Scan history's
    second source was always empty and the failed-run rendering was untestable
    without breaking something for real.
    """
    for day_offset in range(14, 0, -1):
        started = now - timedelta(days=day_offset, minutes=rng.randint(0, 40))
        failed = day_offset == 6
        session.add(
            JobRun(
                job_name=CREATOR_JOB_NAME,
                started_at=started,
                finished_at=started + timedelta(seconds=rng.randint(2, 20)),
                status="failed" if failed else "success",
                stats=(
                    {
                        "creators": len(_MAKERS) + 1,
                        "error": (
                            "Graph refused the directory lookup (403). The app "
                            "registration needs the User.Read.All application "
                            "permission with admin consent."
                        ),
                    }
                    if failed
                    else {
                        "creators": len(_MAKERS) + 1,
                        "resolved": len(_MAKERS),
                        "unresolved": 1,
                        "lookup_errors": 0,
                    }
                ),
            )
        )


async def clear() -> dict[str, int]:
    """Remove all seeded data, leaving credentials and accounts intact."""
    async with SessionLocal() as session:
        await session.execute(delete(JobRun))
        await session.execute(delete(AgentCreator))
        await session.execute(delete(TelemetrySnapshot))
        await session.execute(delete(JudgeResult))
        await session.execute(delete(Finding))
        await session.execute(delete(AgentScore))
        await session.execute(delete(Scan))
        await session.execute(delete(Agent))
        await session.execute(delete(Environment))
        # Clear the persona too: an admin still pointed at a demo maker after
        # the data is gone gets an empty personal view rather than no personal
        # view, which looks like the feature is broken.
        await _bind_persona(session, None)
        await session.commit()
    return {"cleared": 1}


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo agent-quality data.")
    parser.add_argument("--agents", type=int, default=40)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--clear", action="store_true", help="Clear data and exit")
    args = parser.parse_args()

    # psycopg async needs a SelectorEventLoop on Windows (no-op elsewhere).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    if args.clear:
        asyncio.run(clear())
        print("Demo data cleared.")
        return 0

    stats = asyncio.run(seed(agents=args.agents, reset=args.reset))
    print(
        f"Seeded {stats['agents']} agents across {stats['environments']} environments "
        f"with {stats['scans']} scans and {stats['findings']} findings."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
