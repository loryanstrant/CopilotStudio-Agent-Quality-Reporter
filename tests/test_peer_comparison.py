"""You, your team and your organisation — and the four ways a team goes missing.

The disclosure rule is the reason most of this file exists: a team average drawn
from a small group, next to the viewer's own figure, gives away an individual's
number. So the interesting assertions are about what is *not* returned, and
about telling the four "no team" cases apart — because the sentence shown on
screen must not imply a problem with the reader's directory record when the real
reason is that they have never created an agent.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api.metrics import MIN_TEAM_PEERS, peer_comparison
from shared.db import SessionLocal
from shared.models import Agent, AgentCreator, AgentScore, Environment, Scan

ME = "me@contoso.com"
DEPT = "Customer Operations"


async def make_creator(
    session,
    upn: str,
    *,
    department: str | None = DEPT,
    manager_id: str | None = "mgr-1",
    resolved: bool = True,
) -> None:
    session.add(
        AgentCreator(
            upn=upn.lower(),
            display_name=upn.split("@")[0].title(),
            department=department,
            manager_id=manager_id,
            manager_name="Dana Whitfield",
            resolved=resolved,
        )
    )


async def make_agents(session, scan: Scan, upn: str, scores: list[int]) -> None:
    """One agent per score, created by ``upn`` and scored in ``scan``."""
    now = datetime.now(timezone.utc)
    for i, score in enumerate(scores):
        bot = f"{upn}-{i}"
        session.add(
            Agent(
                bot_id=bot,
                display_name=f"{upn} agent {i}",
                created_by_upn=upn,
                created_by_name=upn.split("@")[0].title(),
                created_on=now - timedelta(days=100),
            )
        )
        session.add(
            AgentScore(
                scan_id=scan.id,
                bot_id=bot,
                agent_name=f"{upn} agent {i}",
                score=score,
                grade="C",
                captured_at=now - timedelta(days=1),
            )
        )


async def build(peers: int, *, me_agents: list[int] | None = None, **me_directory):
    """A tenant with ``peers`` colleagues in the viewer's department."""
    async with SessionLocal() as session:
        env = Environment(display_name="Contoso")
        session.add(env)
        await session.flush()
        scan = Scan(environment_id=env.id, source="demo", status="complete")
        session.add(scan)
        await session.flush()

        if me_agents is not None:
            await make_creator(session, ME, **me_directory)
            await make_agents(session, scan, ME, me_agents)
        for i in range(peers):
            upn = f"peer{i}@contoso.com"
            await make_creator(session, upn)
            await make_agents(session, scan, upn, [50, 70])
        # Somebody in another department, under another manager, so
        # "organisation" is wider than "team" under either grouping.
        await make_creator(
            session, "outsider@contoso.com", department="Finance", manager_id="mgr-2"
        )
        await make_agents(session, scan, "outsider@contoso.com", [20])
        await session.commit()


@pytest.mark.asyncio
async def test_three_series_when_the_team_is_big_enough():
    await build(MIN_TEAM_PEERS, me_agents=[80, 90])
    async with SessionLocal() as session:
        result = await peer_comparison(session, upn=ME)

    assert result["mine"] == {"agents": 2, "avg_score": 85}
    assert result["team"]["agents"] == 2
    assert result["team"]["avg_score"] == 60
    assert result["team_label"] == DEPT
    assert result["team_omitted_reason"] is None
    # The organisation is everyone else, including the other department.
    assert result["organisation_size"] == MIN_TEAM_PEERS + 1


@pytest.mark.asyncio
async def test_a_team_one_person_short_is_withheld():
    """Four peers is four, whatever the page would look like with a third bar."""
    await build(MIN_TEAM_PEERS - 1, me_agents=[80])
    async with SessionLocal() as session:
        result = await peer_comparison(session, upn=ME)

    assert result["team"] is None
    assert result["team_label"] is None
    assert result["team_size"] == MIN_TEAM_PEERS - 1
    assert result["team_omitted_reason"] == "too_small"


@pytest.mark.asyncio
async def test_a_department_of_one_is_not_an_error():
    await build(0, me_agents=[80])
    async with SessionLocal() as session:
        result = await peer_comparison(session, upn=ME)

    assert result["team"] is None
    assert result["mine"]["agents"] == 1
    assert result["organisation"]["avg_score"] == 20


@pytest.mark.asyncio
async def test_the_manager_fallback_does_not_relax_the_threshold():
    """A department of one becoming a manager group of two is still two."""
    async with SessionLocal() as session:
        env = Environment(display_name="Contoso")
        session.add(env)
        await session.flush()
        scan = Scan(environment_id=env.id, source="demo", status="complete")
        session.add(scan)
        await session.flush()
        await make_creator(session, ME, department=None, manager_id="mgr-9")
        await make_agents(session, scan, ME, [70])
        for i in range(2):
            upn = f"sibling{i}@contoso.com"
            await make_creator(session, upn, department=None, manager_id="mgr-9")
            await make_agents(session, scan, upn, [40])
        await session.commit()

    async with SessionLocal() as session:
        result = await peer_comparison(session, upn=ME)
    assert result["team"] is None
    assert result["team_size"] == 2
    assert result["team_omitted_reason"] == "too_small"


@pytest.mark.asyncio
async def test_someone_who_has_never_created_an_agent_is_told_why():
    """The lookup is scoped to creators, so a viewer with no agents has no team.

    This must not read as "your directory record is incomplete" — it is a
    consequence of not syncing the whole tenant, which was the point.
    """
    await build(MIN_TEAM_PEERS)
    async with SessionLocal() as session:
        result = await peer_comparison(session, upn="newcomer@contoso.com")

    assert result["mine"] == {"agents": 0, "avg_score": None}
    assert result["team"] is None
    assert result["team_omitted_reason"] == "not_a_creator"
    assert result["organisation"]["avg_score"] is not None


@pytest.mark.asyncio
async def test_an_unresolved_creator_is_distinguished_from_an_unknown_team():
    await build(MIN_TEAM_PEERS, me_agents=[80], resolved=False)
    async with SessionLocal() as session:
        unresolved = await peer_comparison(session, upn=ME)
    assert unresolved["team_omitted_reason"] == "directory_unresolved"

    async with SessionLocal() as session:
        row = await session.get(AgentCreator, ME)
        row.resolved = True
        row.department = None
        row.manager_id = None
        await session.commit()
    async with SessionLocal() as session:
        unknown = await peer_comparison(session, upn=ME)
    assert unknown["team_omitted_reason"] == "unknown_team"


@pytest.mark.asyncio
async def test_a_blank_department_does_not_become_one_enormous_team():
    """Nobody is anybody's colleague by both having no department."""
    async with SessionLocal() as session:
        env = Environment(display_name="Contoso")
        session.add(env)
        await session.flush()
        scan = Scan(environment_id=env.id, source="demo", status="complete")
        session.add(scan)
        await session.flush()
        await make_creator(session, ME, department="  ", manager_id=None)
        await make_agents(session, scan, ME, [70])
        for i in range(MIN_TEAM_PEERS + 2):
            upn = f"nodept{i}@contoso.com"
            await make_creator(session, upn, department=None, manager_id=None)
            await make_agents(session, scan, upn, [40])
        await session.commit()

    async with SessionLocal() as session:
        result = await peer_comparison(session, upn=ME)
    assert result["team"] is None
    assert result["team_omitted_reason"] == "unknown_team"


@pytest.mark.asyncio
async def test_percentile_and_period_are_stated():
    await build(MIN_TEAM_PEERS, me_agents=[95, 95])
    async with SessionLocal() as session:
        result = await peer_comparison(session, upn=ME)

    # Measured against the organisation — a team of six makes a team-relative
    # percentile arithmetic rather than information.
    assert result["percentile"]["avg_score"] == 100
    assert result["percentile"]["agents"] == 100
    assert result["period_from"] and result["period_to"], "the panel names the period"


@pytest.mark.asyncio
async def test_an_unscored_creator_does_not_average_as_zero():
    """No score is not a score of nought, in either direction."""
    await build(MIN_TEAM_PEERS, me_agents=[])
    async with SessionLocal() as session:
        # A creator with an agent that has never been scored.
        session.add(
            Agent(bot_id="never-scored", display_name="New", created_by_upn=ME)
        )
        await session.commit()
    async with SessionLocal() as session:
        result = await peer_comparison(session, upn=ME)

    assert result["mine"]["avg_score"] is None
    assert result["percentile"]["avg_score"] is None
    assert result["team"]["avg_score"] == 60
