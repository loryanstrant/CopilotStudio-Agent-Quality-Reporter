"""The creator directory sync: what it looks up, and what it refuses to.

The claims worth defending here are less about happy-path parsing and more about
the boundaries the owner set on this feature:

- it looks up **only** UPNs already stamped on an agent, one at a time, and the
  client has no way to enumerate the directory;
- a creator Graph cannot resolve is **kept**, so their agents never disappear;
- a missing consent fails the run, records why, and never fails the scan.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from shared.db import SessionLocal
from shared.models import Agent, AgentCreator, JobRun
from worker.creators import (
    CreatorSyncSkipped,
    JOB_NAME,
    pending_upns,
    sync_creators,
)
from worker.graph import GraphConsentError, GraphNotFound, GraphUserLookup

RESOLVED = "ava@contoso.com"
LEAVER = "gone@contoso.com"


class FakeLookup:
    """Stands in for GraphUserLookup, recording every UPN it was asked about."""

    def __init__(self, *, directory: dict[str, dict], consent: bool = True) -> None:
        self.directory = directory
        self.consent = consent
        self.asked: list[str] = []

    async def __aenter__(self) -> "FakeLookup":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def get_user(self, upn: str) -> dict:
        self.asked.append(upn)
        if not self.consent:
            raise GraphConsentError("needs User.Read.All")
        try:
            return self.directory[upn]
        except KeyError:
            raise GraphNotFound(upn) from None


def entry(name: str, *, department: str | None = None) -> dict:
    return {
        "entra_user_id": f"id-{name}",
        "upn": name,
        "display_name": name.split("@")[0].title(),
        "department": department,
        "job_title": "Analyst",
        "office_location": "Melbourne",
        "manager_id": "mgr-1",
        "manager_name": "Dana Whitfield",
    }


async def seed_agents(upns: list[str]) -> None:
    async with SessionLocal() as session:
        for i, upn in enumerate(upns):
            session.add(
                Agent(
                    bot_id=f"bot-{i}",
                    display_name=f"Agent {i}",
                    created_by_upn=upn,
                    created_by_name=f"Maker {i}",
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_only_creator_upns_are_looked_up():
    """The sync's input is the agents table, not the directory.

    A UPN nobody has built an agent with is never asked about — that is the
    difference between this feature and the tenant-wide sync that was ruled out.
    """
    await seed_agents([RESOLVED, RESOLVED, LEAVER])
    lookup = FakeLookup(directory={RESOLVED: entry(RESOLVED, department="Ops")})

    stats = await sync_creators(SessionLocal, lookup_factory=lambda: lookup)

    assert sorted(lookup.asked) == sorted([RESOLVED, LEAVER])
    assert stats["resolved"] == 1
    assert stats["unresolved"] == 1


@pytest.mark.asyncio
async def test_an_unresolvable_creator_is_kept():
    """A leaver or service principal keeps its row, with the reason."""
    await seed_agents([LEAVER])
    await sync_creators(
        SessionLocal, lookup_factory=lambda: FakeLookup(directory={})
    )

    async with SessionLocal() as session:
        row = await session.get(AgentCreator, LEAVER)
    assert row is not None, "dropping the row would lose this person's agents"
    assert row.resolved is False
    assert row.error


@pytest.mark.asyncio
async def test_details_are_stored_for_the_team_grouping():
    await seed_agents([RESOLVED])
    await sync_creators(
        SessionLocal,
        lookup_factory=lambda: FakeLookup(
            directory={RESOLVED: entry(RESOLVED, department="Customer Operations")}
        ),
    )

    async with SessionLocal() as session:
        row = await session.get(AgentCreator, RESOLVED)
    assert row.display_name == "Ava"
    assert row.department == "Customer Operations"
    assert row.manager_id == "mgr-1"
    assert row.manager_name == "Dana Whitfield"
    assert row.resolved is True


@pytest.mark.asyncio
async def test_missing_consent_fails_the_run_and_says_why():
    """One 403 ends the sync: every other lookup would return the same thing."""
    await seed_agents([RESOLVED, LEAVER])
    lookup = FakeLookup(directory={}, consent=False)

    stats = await sync_creators(SessionLocal, lookup_factory=lambda: lookup)

    assert len(lookup.asked) == 1, "should stop rather than collect the same 403"
    assert "User.Read.All" in stats["error"]

    async with SessionLocal() as session:
        run = await session.scalar(
            select(JobRun).order_by(JobRun.started_at.desc()).limit(1)
        )
    assert run.job_name == JOB_NAME
    assert run.status == "failed"
    assert "User.Read.All" in run.stats["error"]


@pytest.mark.asyncio
async def test_a_successful_run_is_recorded_under_its_own_kind():
    """Not "users" — that is the siblings' word for a whole-tenant import."""
    await seed_agents([RESOLVED])
    await sync_creators(
        SessionLocal,
        lookup_factory=lambda: FakeLookup(directory={RESOLVED: entry(RESOLVED)}),
    )

    async with SessionLocal() as session:
        run = await session.scalar(
            select(JobRun).order_by(JobRun.started_at.desc()).limit(1)
        )
    assert run.job_name == "creators"
    assert run.status == "success"
    assert run.stats["resolved"] == 1


@pytest.mark.asyncio
async def test_fresh_creators_are_skipped_but_unresolved_ones_retry():
    """A stable tenant makes no Graph calls; a failed lookup is tried again."""
    await seed_agents([RESOLVED, LEAVER])
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        session.add(
            AgentCreator(upn=RESOLVED, resolved=True, updated_at=now - timedelta(days=1))
        )
        session.add(
            AgentCreator(upn=LEAVER, resolved=False, updated_at=now - timedelta(days=1))
        )
        await session.commit()

    async with SessionLocal() as session:
        pending = await pending_upns(session)
    assert pending == [LEAVER]

    async with SessionLocal() as session:
        stale = await session.get(AgentCreator, RESOLVED)
        stale.updated_at = now - timedelta(days=30)
        await session.commit()
    async with SessionLocal() as session:
        assert sorted(await pending_upns(session)) == sorted([RESOLVED, LEAVER])


@pytest.mark.asyncio
async def test_nothing_to_do_is_not_a_failure():
    """No creators means the sync did not run, which is not the same as failing."""
    with pytest.raises(CreatorSyncSkipped):
        await sync_creators(
            SessionLocal, lookup_factory=lambda: FakeLookup(directory={})
        )


@pytest.mark.asyncio
async def test_the_client_can_only_ever_request_one_named_user():
    """The URL shape is the enforcement of "not a tenant sync".

    ``GraphUserLookup`` exposes no collection call at all, so this asserts what a
    lookup actually puts on the wire: a single ``/users/{upn}``, with no filter
    over the collection and no paging.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": "abc",
                "userPrincipalName": RESOLVED,
                "displayName": "Ava",
                "department": "Ops",
                "manager": {"id": "mgr-1", "displayName": "Dana"},
            },
        )

    lookup = GraphUserLookup(
        tenant_id="t", client_id="c", client_secret="s"
    )
    lookup._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    lookup.token = lambda: _token()  # type: ignore[method-assign]

    details = await lookup.get_user(RESOLVED)
    await lookup.aclose()

    assert details["department"] == "Ops"
    assert details["manager_name"] == "Dana"
    assert len(seen) == 1
    url = seen[0].url
    assert url.path == f"/v1.0/users/{RESOLVED}"
    assert "$filter" not in str(url), "a filter would mean querying the collection"
    assert not hasattr(GraphUserLookup, "iter_users")


async def _token() -> str:
    return "fake-token"
