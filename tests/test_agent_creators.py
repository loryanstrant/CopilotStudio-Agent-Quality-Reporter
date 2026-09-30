"""The Agent creators listing.

This is not a tenant directory and the tests say so. The app holds no directory
data — the worker reads Dataverse, not Graph — so the only people it can list
are the makers Copilot Studio stamps on agents. What matters is that the
grouping is right, the scores are current, and the default order answers the
question the page is opened for.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api.auth import create_access_token
from shared.db import SessionLocal
from shared.models import (
    Agent,
    AgentCreator,
    AgentScore,
    AppConfig,
    AppUser,
    Environment,
    Finding,
    Scan,
)
from shared.security import hash_password

NOW = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


async def _admin_headers() -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    return {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


async def _seed() -> None:
    """Two makers with different volumes and different quality, plus one agent
    whose maker is unknown."""
    async with SessionLocal() as s:
        env = Environment(display_name="Contoso", enabled=True)
        s.add(env)
        await s.flush()

        scan = Scan(
            environment_id=env.id,
            source="demo",
            status="complete",
            started_at=NOW,
            agent_count=4,
        )
        s.add(scan)
        await s.flush()

        # Ada: two agents, good. Grace: one agent, poor. Plus one orphan.
        spec = [
            ("bot-1", "Ada Lovelace", "Ada@contoso.com", 90, "A", 0),
            # Deliberately different casing: Dataverse and Entra disagree, and
            # one person must not become two rows because of it.
            ("bot-2", "Ada Lovelace", "ada@contoso.com", 80, "B", 2),
            ("bot-3", "Grace Hopper", "grace@contoso.com", 50, "F", 5),
            ("bot-4", None, None, 70, "C", 0),
        ]
        for bot_id, name, upn, score, grade, fails in spec:
            s.add(
                Agent(
                    bot_id=bot_id,
                    environment_id=env.id,
                    display_name=f"Agent {bot_id}",
                    created_by_name=name,
                    created_by_upn=upn,
                    last_seen=NOW,
                )
            )
            s.add(
                AgentScore(
                    scan_id=scan.id,
                    environment_id=env.id,
                    bot_id=bot_id,
                    agent_name=f"Agent {bot_id}",
                    score=score,
                    grade=grade,
                    captured_at=NOW,
                )
            )
            for j in range(fails):
                s.add(
                    Finding(
                        scan_id=scan.id,
                        rule_id=f"R-{j}",
                        name=f"Rule {j}",
                        severity="major",
                        status="fail",
                        agent_name=f"Agent {bot_id}",
                    )
                )
        await s.commit()


@pytest.mark.asyncio
async def test_creators_are_grouped_per_person(client):
    await _seed()
    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    by_upn = {r["upn"].lower(): r for r in rows}

    assert set(by_upn) == {"ada@contoso.com", "grace@contoso.com"}
    assert by_upn["ada@contoso.com"]["agents"] == 2
    assert by_upn["ada@contoso.com"]["avg_score"] == 85
    assert by_upn["ada@contoso.com"]["grades"]["A"] == 1
    assert by_upn["ada@contoso.com"]["grades"]["B"] == 1
    assert by_upn["ada@contoso.com"]["open_findings"] == 2


@pytest.mark.asyncio
async def test_casing_does_not_split_one_person_into_two_rows(client):
    """Dataverse and Entra disagree about casing in practice."""
    await _seed()
    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    assert len([r for r in rows if r["upn"].lower() == "ada@contoso.com"]) == 1


@pytest.mark.asyncio
async def test_an_agent_with_no_recorded_maker_belongs_to_nobody(client):
    """It must not become a blank row, and must not be silently attributed."""
    await _seed()
    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    assert all(r["upn"] for r in rows)
    assert sum(r["agents"] for r in rows) == 3  # not 4


@pytest.mark.asyncio
async def test_worst_average_sorts_first(client):
    """The page is opened to answer "who needs attention", so the default order
    should answer it on arrival rather than after a click."""
    await _seed()
    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    assert rows[0]["upn"].lower() == "grace@contoso.com"


@pytest.mark.asyncio
async def test_a_creator_with_nothing_scored_sorts_last(client):
    """An unknown is not a problem, and must not outrank a real one."""
    async with SessionLocal() as s:
        env = Environment(display_name="Contoso", enabled=True)
        s.add(env)
        await s.flush()
        s.add(
            Agent(
                bot_id="bot-9",
                environment_id=env.id,
                display_name="Unscanned",
                created_by_name="New Starter",
                created_by_upn="new@contoso.com",
                last_seen=NOW,
            )
        )
        await s.commit()
    await _seed()

    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    assert rows[-1]["upn"] == "new@contoso.com"
    assert rows[-1]["avg_score"] is None


@pytest.mark.asyncio
async def test_listing_is_organisation_gated(client):
    """It is a list of named colleagues with their work quality against their
    names, so it is not open to any signed-in user."""
    async with SessionLocal() as s:
        s.add(AppConfig(id=1, org_view_group_id="gggggggg-gggg-gggg-gggg-gggggggggggg"))
        await s.commit()

    token = create_access_token(
        "ada@contoso.com", "viewer", oid="oid-1", upn="ada@contoso.com"
    )
    r = await client.get(
        "/reports/agent-creators", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_scores_come_from_the_most_recent_scan(client):
    """A creator's average should reflect where their agents are now, not
    whichever scan happened to run last in their environment."""
    await _seed()
    async with SessionLocal() as s:
        env = await s.scalar(
            __import__("sqlalchemy").select(Environment).limit(1)
        )
        later = Scan(
            environment_id=env.id,
            source="demo",
            status="complete",
            started_at=NOW + timedelta(days=1),
            agent_count=1,
        )
        s.add(later)
        await s.flush()
        s.add(
            AgentScore(
                scan_id=later.id,
                environment_id=env.id,
                bot_id="bot-3",
                agent_name="Agent bot-3",
                score=95,
                grade="A",
                captured_at=NOW + timedelta(days=1),
            )
        )
        await s.commit()

    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    grace = next(r for r in rows if r["upn"] == "grace@contoso.com")
    assert grace["avg_score"] == 95
    assert grace["grades"]["A"] == 1


# --------------------------------------------------------------------------- #
# Each creator's agents, so clicking a name on the page can show them
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_each_creator_carries_their_own_agents(client):
    """The page filters in place rather than routing to a per-creator page, so
    the agents come down with the creators rather than from a second call."""
    await _seed()
    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    ada = next(r for r in rows if r["upn"].lower() == "ada@contoso.com")

    assert len(ada["agent_list"]) == ada["agents"] == 2
    assert {a["bot_id"] for a in ada["agent_list"]} == {"bot-1", "bot-2"}
    # Enough to render a row and click through to the scorecard.
    bot2 = next(a for a in ada["agent_list"] if a["bot_id"] == "bot-2")
    assert bot2["agent_name"] == "Agent bot-2"
    assert (bot2["score"], bot2["grade"], bot2["open_findings"]) == (80, "B", 2)
    assert bot2["environment_name"] == "Contoso"
    assert bot2["scan_id"] is not None


@pytest.mark.asyncio
async def test_a_creators_agents_are_worst_first(client):
    """Opening one person's list is a request to find what needs fixing."""
    await _seed()
    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    ada = next(r for r in rows if r["upn"].lower() == "ada@contoso.com")
    assert [a["score"] for a in ada["agent_list"]] == [80, 90]


@pytest.mark.asyncio
async def test_an_unscanned_agent_is_listed_with_no_score(client):
    """It belongs to its creator whether or not a scan has reached it, and it
    sorts last — an unknown is not a problem."""
    async with SessionLocal() as s:
        env = Environment(display_name="Contoso", enabled=True)
        s.add(env)
        await s.flush()
        s.add(
            Agent(
                bot_id="bot-9",
                environment_id=env.id,
                display_name="Unscanned",
                created_by_name="Ada Lovelace",
                created_by_upn="ada@contoso.com",
                last_seen=NOW,
            )
        )
        await s.commit()
    await _seed()

    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    ada = next(r for r in rows if r["upn"].lower() == "ada@contoso.com")
    assert ada["agent_list"][-1]["bot_id"] == "bot-9"
    assert ada["agent_list"][-1]["score"] is None
    assert ada["agent_list"][-1]["agent_name"] == "Unscanned"


@pytest.mark.asyncio
async def test_an_unresolved_creators_address_is_shown_readably_but_stored_intact(client):
    """A former user can reach this page with their Entra object id run into
    their address. The row shows the address part; the stored value is what the
    app still reports, because it is the thing to quote when somebody asks why
    the lookup failed."""
    mashed = "20a43a6b4ea043858a0efbb9e20ce4cfjustin.bell@contoso.com"
    async with SessionLocal() as s:
        env = Environment(display_name="Contoso", enabled=True)
        s.add(env)
        await s.flush()
        s.add(
            Agent(
                bot_id="bot-7",
                environment_id=env.id,
                display_name="Leavers bot",
                created_by_name="Justin Bell",
                created_by_upn=mashed,
                last_seen=NOW,
            )
        )
        s.add(AgentCreator(upn=mashed.lower(), resolved=False, error="not found"))
        await s.commit()

    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    row = next(r for r in rows if r["upn"] == mashed)
    assert row["directory_resolved"] is False
    assert row["upn"] == mashed
    assert row["upn_display"] == "justin.bell@contoso.com"


@pytest.mark.asyncio
async def test_an_ordinary_address_is_displayed_exactly_as_stored(client):
    await _seed()
    rows = (
        await client.get("/reports/agent-creators", headers=await _admin_headers())
    ).json()
    assert all(r["upn_display"] == r["upn"] for r in rows)
