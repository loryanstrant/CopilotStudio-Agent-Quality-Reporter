"""Seed synthetic agent-quality data so the dashboards render without Dataverse.

Generates plausible fictional environments, agents, scans, findings and judge
results — no Dataverse or Azure OpenAI calls. Use it to explore the UI locally,
or to demo the reporter before wiring up a tenant.

Run inside the container / venv::

    python -m scripts.seed_demo                   # 3 environments, ~18 agents
    python -m scripts.seed_demo --agents 40 --reset
    python -m scripts.seed_demo --clear

``--reset`` clears the scan/agent tables first. This never touches credentials
(``app_config``). It makes exactly one change to ``app_users``: it points the
local admin account at one of the seeded agent creators, so the personal pages
can be reached without an Entra tenant (see :func:`_bind_local_admin`).
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from shared.db import SessionLocal
from shared.models import (
    Agent,
    AgentScore,
    AppUser,
    Environment,
    Finding,
    JudgeResult,
    Scan,
    TelemetrySnapshot,
)

_ENVIRONMENTS = [
    ("Contoso (default)", "https://contoso.crm6.dynamics.com"),
    ("Contoso — UAT", "https://contoso-uat.crm6.dynamics.com"),
    ("Contoso — Dev", "https://contoso-dev.crm6.dynamics.com"),
]

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
# agent used to be created by one address, "demo@contoso.local", which made the
# Agent creators listing a single row and the personal view either everything or
# nothing — neither of which is what either page looks like in a real tenant.
# The weights give a couple of prolific makers, a middle, and a long tail.
_MAKERS = [
    ("Ava Bennett", "ava.bennett@contoso.local", 6),
    ("Noah Okafor", "noah.okafor@contoso.local", 5),
    ("Mia Nguyen", "mia.nguyen@contoso.local", 4),
    ("Priya Raman", "priya.raman@contoso.local", 3),
    ("Tom Hargreaves", "tom.hargreaves@contoso.local", 2),
    ("Sofia Marchetti", "sofia.marchetti@contoso.local", 1),
]

# The maker the local admin account is bound to when demo data is loaded, so
# whoever is evaluating the product lands on a personal view with agents in it.
_DEMO_ADMIN_MAKER = _MAKERS[0]

# Any UPN in this domain is demo data, which is how _bind_local_admin can tell
# a binding it created from one a real deployment set deliberately.
_DEMO_DOMAIN = "@contoso.local"

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


async def _bind_local_admin(session, upn: str | None) -> None:
    """Point the local admin account at a demo maker (or unbind it).

    Agents are attributed by their creator's UPN, so a password account has no
    "me" to filter a personal view down to and the personal pages are
    unreachable — which meant nobody evaluating this product with demo data
    could see pages the README advertises.

    Only a NULL binding or a previous demo binding is touched. A deployment
    that has deliberately pointed its break-glass account at a real directory
    UPN keeps it, because seeding demo data must never quietly reassign
    somebody's identity.
    """
    admins = (
        (await session.execute(select(AppUser).where(AppUser.role == "admin")))
        .scalars()
        .all()
    )
    for admin in admins:
        if admin.upn and not admin.upn.endswith(_DEMO_DOMAIN):
            continue
        admin.upn = upn


async def seed(agents: int = 18, reset: bool = True) -> dict[str, int]:
    """Populate the reporting tables with plausible fictional data.

    Returns a stats dict so callers (CLI and the admin endpoint) can report what
    was created.
    """
    rng = random.Random(20260914)
    now = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        if reset:
            # Fact tables only — app_config is untouched, and app_users only
            # gains the admin binding set at the end of this function.
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
            maker = (
                _DEMO_ADMIN_MAKER
                if i == 0
                else rng.choices(_MAKERS, weights=maker_weights, k=1)[0]
            )
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

        await _bind_local_admin(session, _DEMO_ADMIN_MAKER[1])
        await session.commit()

    return {
        "environments": len(_ENVIRONMENTS),
        "agents": len(agent_rows),
        "scans": len(scan_rows),
        "findings": total_findings,
    }


async def clear() -> dict[str, int]:
    """Remove all seeded data, leaving credentials and accounts intact."""
    async with SessionLocal() as session:
        await session.execute(delete(TelemetrySnapshot))
        await session.execute(delete(JudgeResult))
        await session.execute(delete(Finding))
        await session.execute(delete(AgentScore))
        await session.execute(delete(Scan))
        await session.execute(delete(Agent))
        await session.execute(delete(Environment))
        # Unbind too: an admin still pointed at a demo maker after the data is
        # gone gets an empty personal view rather than no personal view, which
        # looks like the feature is broken.
        await _bind_local_admin(session, None)
        await session.commit()
    return {"cleared": 1}


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo agent-quality data.")
    parser.add_argument("--agents", type=int, default=18)
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
