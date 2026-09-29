"""Demo data, and the personal view it is supposed to make reachable.

Demo data is how anybody evaluates this product before wiring up a tenant, so
it has to produce the shapes the real thing produces: several makers rather
than one, judge prose as lists rather than sentences, and telemetry that is
there to be looked at. It also has to make the personal pages reachable, which
they were not without an Entra tenant.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from scripts.seed_demo import _DEMO_ADMIN_MAKER, clear, seed
from shared.db import SessionLocal
from shared.models import Agent, AppUser, JudgeResult, TelemetrySnapshot
from shared.security import hash_password


async def _add_admin(upn: str | None = None) -> None:
    async with SessionLocal() as s:
        s.add(
            AppUser(
                username="admin",
                password_hash=hash_password("pw"),
                role="admin",
                upn=upn,
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_agents_are_spread_across_several_makers():
    """Every agent used to be created by one address, which made the Agent
    creators listing a single row."""
    await seed(agents=18, reset=True)
    async with SessionLocal() as s:
        upns = {a.created_by_upn for a in (await s.execute(select(Agent))).scalars()}
    assert len(upns) > 1
    assert _DEMO_ADMIN_MAKER[1] in upns


@pytest.mark.asyncio
async def test_judge_prose_is_written_as_lists():
    """top_strengths and recommended_changes are JSON list columns, and the
    judge panel renders them as bullets. Strings rendered as one run-on line."""
    await seed(agents=6, reset=True)
    async with SessionLocal() as s:
        results = (await s.execute(select(JudgeResult))).scalars().all()
    assert results
    for r in results:
        assert isinstance(r.top_strengths, list)
        assert isinstance(r.top_weaknesses, list)
        assert isinstance(r.recommended_changes, list)


@pytest.mark.asyncio
async def test_telemetry_is_seeded_so_the_app_insights_panel_is_not_empty():
    await seed(agents=12, reset=True)
    async with SessionLocal() as s:
        snapshots = (await s.execute(select(TelemetrySnapshot))).scalars().all()
    assert snapshots
    assert all(t.run_count and t.run_count > 0 for t in snapshots)


@pytest.mark.asyncio
async def test_seeding_binds_the_local_admin_to_a_maker():
    """Otherwise the personal pages the README advertises cannot be reached at
    all without an Entra tenant."""
    await _add_admin()
    await seed(agents=6, reset=True)
    async with SessionLocal() as s:
        admin = await s.scalar(select(AppUser).where(AppUser.username == "admin"))
    assert admin.upn == _DEMO_ADMIN_MAKER[1]


@pytest.mark.asyncio
async def test_the_bound_admin_actually_owns_agents():
    """A binding to a maker with no agents would be worse than none: the page
    would load and be empty, which reads as a broken feature."""
    await _add_admin()
    await seed(agents=6, reset=True)
    async with SessionLocal() as s:
        mine = (
            await s.execute(
                select(Agent).where(Agent.created_by_upn == _DEMO_ADMIN_MAKER[1])
            )
        ).scalars().all()
    assert mine


@pytest.mark.asyncio
async def test_a_real_binding_is_never_reassigned():
    """Seeding demo data must not quietly repoint somebody's break-glass
    account at a fictional person."""
    await _add_admin(upn="real.person@contoso.com")
    await seed(agents=6, reset=True)
    async with SessionLocal() as s:
        admin = await s.scalar(select(AppUser).where(AppUser.username == "admin"))
    assert admin.upn == "real.person@contoso.com"


@pytest.mark.asyncio
async def test_clearing_demo_data_unbinds_the_admin():
    """An admin still bound after the data is gone gets an empty personal view
    rather than no personal view, which looks like a bug."""
    await _add_admin()
    await seed(agents=6, reset=True)
    await clear()
    async with SessionLocal() as s:
        admin = await s.scalar(select(AppUser).where(AppUser.username == "admin"))
    assert admin.upn is None


@pytest.mark.asyncio
async def test_a_bound_admin_reaches_the_personal_view(client):
    """The whole point: password sign-in, no Entra, personal pages reachable."""
    await _add_admin()
    await seed(agents=6, reset=True)
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    me = (await client.get("/auth/me", headers=headers)).json()
    assert me["has_personal_view"] is True
    assert me["upn"] == _DEMO_ADMIN_MAKER[1]

    summary = (await client.get("/reports/me/summary", headers=headers)).json()
    assert summary["has_data"] is True
    assert summary["agents"] > 0


@pytest.mark.asyncio
async def test_an_unbound_local_admin_still_has_no_personal_view(client):
    """The default is unchanged: no directory identity, no "me" to filter to."""
    await _add_admin()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get("/auth/me", headers=headers)).json()
    assert me["has_personal_view"] is False
    assert me["upn"] is None
