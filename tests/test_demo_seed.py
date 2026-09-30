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
from shared.models import (
    Agent,
    AppConfig,
    AppUser,
    Environment,
    JudgeResult,
    TelemetrySnapshot,
)
from shared.security import hash_password
from worker.scan import run_scan


async def _add_admin() -> None:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()


async def _persona() -> str | None:
    async with SessionLocal() as s:
        cfg = await s.get(AppConfig, 1)
        return cfg.demo_persona_upn if cfg else None


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
async def test_seeding_sets_the_demo_persona():
    """Otherwise the personal pages the README advertises cannot be reached at
    all without an Entra tenant."""
    await _add_admin()
    await seed(agents=6, reset=True)
    assert await _persona() == _DEMO_ADMIN_MAKER[1]


@pytest.mark.asyncio
async def test_the_persona_actually_owns_agents():
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
async def test_an_sso_user_never_inherits_the_persona():
    """The persona exists so whoever loaded the demo data can see the pages it
    unlocks. A real signed-in person keeps their own identity."""
    from api.auth import CurrentUser, personal_view_upn

    await _add_admin()
    await seed(agents=6, reset=True)
    async with SessionLocal() as s:
        real = CurrentUser(
            username="ada@contoso.com", role="viewer", oid="oid-1", upn="ada@contoso.com"
        )
        assert await personal_view_upn(real, s) == "ada@contoso.com"


@pytest.mark.asyncio
async def test_a_local_viewer_does_not_get_the_persona():
    """Only the account that could have loaded the demo data stands in for it."""
    from api.auth import CurrentUser, personal_view_upn

    await _add_admin()
    await seed(agents=6, reset=True)
    async with SessionLocal() as s:
        viewer = CurrentUser(username="reader", role="viewer")
        assert await personal_view_upn(viewer, s) is None


@pytest.mark.asyncio
async def test_clearing_demo_data_clears_the_persona():
    """An admin still bound after the data is gone gets an empty personal view
    rather than no personal view, which looks like a bug."""
    await _add_admin()
    await seed(agents=6, reset=True)
    await clear()
    assert await _persona() is None


@pytest.mark.asyncio
async def test_a_real_scan_retires_the_persona(monkeypatch):
    """Once there is real data the persona points at a maker with no agents —
    a personal view that loads and is empty, which reads as broken.

    Only the Dataverse fetch is stubbed. The scan itself runs for real, so this
    exercises the retirement where it actually lives rather than asserting that
    a helper was called.
    """
    import worker.scan as scan_mod
    from shared.db import SessionLocal as SL

    await _add_admin()
    await seed(agents=6, reset=True)
    assert await _persona() is not None

    async with SessionLocal() as s:
        env = (await s.execute(select(Environment))).scalars().first()
        env_id = env.id

    async def _fake_gather(session, *, source, environment_id):
        return [{"display_name": "Real Agent", "instructions": "x" * 250}], env

    monkeypatch.setattr(scan_mod, "_gather_agents", _fake_gather)
    await run_scan(SL, source="dataverse", environment_id=env_id)
    assert await _persona() is None


@pytest.mark.asyncio
async def test_a_demo_scan_does_not_retire_the_persona(monkeypatch):
    """Re-running the demo must not switch the personal pages back off."""
    import worker.scan as scan_mod
    from shared.db import SessionLocal as SL

    await _add_admin()
    await seed(agents=6, reset=True)

    async def _fake_gather(session, *, source, environment_id):
        return [{"display_name": "Demo Agent", "instructions": "x" * 250}], None

    monkeypatch.setattr(scan_mod, "_gather_agents", _fake_gather)
    await run_scan(SL, source="demo")
    assert await _persona() == _DEMO_ADMIN_MAKER[1]


@pytest.mark.asyncio
async def test_the_persona_makes_the_personal_view_reachable(client):
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
async def test_a_local_admin_without_a_persona_has_no_personal_view(client):
    """The default is unchanged: no directory identity, no "me" to filter to."""
    await _add_admin()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get("/auth/me", headers=headers)).json()
    assert me["has_personal_view"] is False
    assert me["upn"] is None


@pytest.mark.asyncio
async def test_seeded_departments_are_big_enough_to_show_a_team():
    """The comparison must actually appear on demo data, without relaxing the rule.

    Random department assignment over a handful of makers produced departments
    of three, so the team series was withheld and the feature the demo exists to
    show never rendered. Round-robin over fourteen makers guarantees six peers
    each. The threshold itself is never lowered — this asserts the population is
    right, not that the rule was bent.
    """
    from api.metrics import MIN_TEAM_PEERS, peer_comparison

    await seed(agents=40, reset=True)
    async with SessionLocal() as session:
        result = await peer_comparison(session, upn=_DEMO_ADMIN_MAKER[1])

    assert result["team"] is not None, "demo data must exercise the team series"
    assert result["team_size"] >= MIN_TEAM_PEERS
    assert result["team_label"]
    # Two departments, so the team average and the organisation average are
    # different numbers — three identical bars reads as a bug.
    assert result["team"] != result["organisation"]


@pytest.mark.asyncio
async def test_seeded_creators_carry_directory_details_including_one_unresolved():
    """Demo data never calls Graph, so the rows the sync would write are seeded."""
    from shared.models import AgentCreator

    await seed(agents=40, reset=True)
    async with SessionLocal() as session:
        creators = (await session.execute(select(AgentCreator))).scalars().all()

    assert len({c.department for c in creators if c.department} or {}) == 2
    assert all(c.manager_name for c in creators if c.resolved)
    unresolved = [c for c in creators if not c.resolved]
    assert len(unresolved) == 1, "the kept-but-unresolvable creator must be visible"
    assert unresolved[0].error


@pytest.mark.asyncio
async def test_the_run_log_is_seeded_with_a_failure_in_it():
    """Scan history's failure rendering was untestable without breaking something."""
    from api.metrics import scan_history

    await seed(agents=40, reset=True)
    async with SessionLocal() as session:
        rows = await scan_history(session, limit=500)

    directory_runs = [r for r in rows if r["kind"] == "Creator directory"]
    assert len(directory_runs) == 14, "a fortnight of runs"
    failed = [r for r in directory_runs if r["state"] == "failed"]
    assert len(failed) == 1 and failed[0]["error"]
    # A failed scan and a part-finished scan, both otherwise unreachable in a demo.
    assert any(r["state"] == "failed" and r["scan_id"] for r in rows)
    assert any(r["partial"] for r in rows)


@pytest.mark.asyncio
async def test_clearing_demo_data_takes_the_directory_and_run_log_with_it():
    from shared.models import AgentCreator, JobRun

    await seed(agents=6, reset=True)
    await clear()
    async with SessionLocal() as session:
        assert (await session.execute(select(AgentCreator))).scalars().all() == []
        assert (await session.execute(select(JobRun))).scalars().all() == []
