"""Seed synthetic agent-quality data so the dashboards render without Dataverse.

Generates plausible fictional environments, agents, scans, findings and judge
results — no Dataverse or Azure OpenAI calls. Use it to explore the UI locally,
or to demo the reporter before wiring up a tenant.

Run inside the container / venv::

    python -m scripts.seed_demo                   # 3 environments, ~18 agents
    python -m scripts.seed_demo --agents 40 --reset
    python -m scripts.seed_demo --clear

``--reset`` clears the scan/agent tables first. This never touches credentials
(``app_config``) or user accounts (``app_users``).
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
    Environment,
    Finding,
    JudgeResult,
    Scan,
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


async def seed(agents: int = 18, reset: bool = True) -> dict[str, int]:
    """Populate the reporting tables with plausible fictional data.

    Returns a stats dict so callers (CLI and the admin endpoint) can report what
    was created.
    """
    rng = random.Random(20260914)
    now = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        if reset:
            # Fact tables only — app_config and app_users are untouched.
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
        agent_rows: list[Agent] = []
        for i, agent_name in enumerate(names):
            env = env_rows[i % len(env_rows)]
            agent_rows.append(
                Agent(
                    bot_id=str(uuid.uuid4()),
                    environment_id=env.id,
                    display_name=agent_name,
                    schema_name=f"cr123_{agent_name.lower().replace(' ', '_')}",
                    description=None if rng.random() < 0.3 else f"{agent_name} for staff.",
                    publish_state=rng.choice(["Published", "Published", "Draft"]),
                    created_by_name=rng.choice(["Ava Bennett", "Noah Okafor", "Mia Nguyen"]),
                    created_by_upn="demo@contoso.local",
                    created_on=now - timedelta(days=rng.randint(30, 400)),
                    modified_on=now - timedelta(days=rng.randint(0, 30)),
                    last_seen=now,
                )
            )
        session.add_all(agent_rows)
        await session.flush()

        total_findings = 0
        scan_rows: list[Scan] = []

        # One scan per environment per day for the last 14 days, so the history
        # page and the per-agent trend lines have something to draw.
        for day_offset in range(14, -1, -1):
            started = now - timedelta(days=day_offset)
            for env in env_rows:
                env_agents = [a for a in agent_rows if a.environment_id == env.id]
                if not env_agents:
                    continue
                scan = Scan(
                    environment_id=env.id,
                    solution_name="Demo solution",
                    source="demo",
                    status="succeeded",
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
                        fail_chance = 0.32 * (0.6 + day_offset / 25)
                        failed = rng.random() < fail_chance
                        manual = rule_id == "AGT-007"
                        status = "manual" if manual else ("fail" if failed else "pass")
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

                    # Judge results only on the most recent scan, as in a real run.
                    if day_offset == 0:
                        session.add(
                            JudgeResult(
                                scan_id=scan.id,
                                agent_name=agent.display_name,
                                clarity=rng.randint(4, 10),
                                persona_defined=rng.random() < 0.6,
                                scope_discipline=rng.randint(3, 10),
                                output_format_guidance=rng.random() < 0.5,
                                orchestrator_pattern_detected=rng.random() < 0.25,
                                child_pattern_detected=rng.random() < 0.2,
                                summary=f"Instructions for {agent.display_name} are workable but could be tighter.",
                                top_strengths="Clear purpose; sensible tone.",
                                recommended_changes="Add explicit out-of-scope handling and an output format.",
                                skipped=False,
                            )
                        )

                avg = round(sum(scores) / len(scores)) if scores else 0
                scan.score = avg
                scan.grade = _grade(avg)

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
        await session.execute(delete(JudgeResult))
        await session.execute(delete(Finding))
        await session.execute(delete(AgentScore))
        await session.execute(delete(Scan))
        await session.execute(delete(Agent))
        await session.execute(delete(Environment))
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
