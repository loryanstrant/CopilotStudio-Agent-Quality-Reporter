"""Personal view ("agents you created") and the organisation-view gate.

The security-relevant claims here are:

- a personal endpoint scopes to the caller's own identity, and offers no way to
  ask for somebody else's;
- the organisation view is closed to people outside the configured group;
- but an unconfigured group leaves the org view open, so upgrading an existing
  deployment doesn't lock everyone out.

This platform has no user dimension, so "mine" is ``agents.created_by_upn``
matched against the UPN in the token. The seeded data deliberately uses
different casing from the token, because Dataverse and Entra disagree about
casing in practice.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.auth import create_access_token
from shared.db import SessionLocal
from shared.models import (
    Agent,
    AgentScore,
    AppConfig,
    AppUser,
    Environment,
    Finding,
    Scan,
)
from shared.security import hash_password

MY_UPN = "me@contoso.com"
THEIR_UPN = "them@contoso.com"
MY_OID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
GROUP = "cccccccc-cccc-cccc-cccc-cccccccccccc"

MINE = 2
THEIRS = 5


async def _seed_agents() -> None:
    """Two makers with clearly different agent counts, so a leak is obvious."""
    async with SessionLocal() as s:
        env = Environment(display_name="Contoso Prod", enabled=True)
        s.add(env)
        await s.flush()

        scan = Scan(
            environment_id=env.id,
            source="dataverse",
            status="complete",
            started_at=datetime(2026, 9, 1, 8, tzinfo=timezone.utc),
            finished_at=datetime(2026, 9, 1, 9, tzinfo=timezone.utc),
            score=70,
            grade="C",
            agent_count=MINE + THEIRS,
        )
        s.add(scan)
        await s.flush()

        def _add(owner_upn: str, prefix: str, count: int, score: int) -> None:
            for i in range(count):
                name = f"{prefix} {i}"
                bot_id = f"{prefix}-bot-{i}"
                s.add(
                    Agent(
                        environment_id=env.id,
                        bot_id=bot_id,
                        display_name=name,
                        created_by_name=owner_upn,
                        created_by_upn=owner_upn,
                    )
                )
                s.add(
                    AgentScore(
                        scan_id=scan.id,
                        environment_id=env.id,
                        bot_id=bot_id,
                        agent_name=name,
                        score=score,
                        grade="B" if score >= 80 else "D",
                        captured_at=datetime(2026, 9, 1, 9, i, tzinfo=timezone.utc),
                    )
                )
                s.add(
                    Finding(
                        scan_id=scan.id,
                        rule_id="AGT-001",
                        name="Description present",
                        severity="medium",
                        status="fail",
                        weight=5,
                        scope="agent",
                        agent_name=name,
                    )
                )

        # Cased differently from the token on purpose — the comparison has to be
        # case-insensitive.
        _add("Me@Contoso.com", "mine", MINE, 85)
        _add(THEIR_UPN, "theirs", THEIRS, 40)
        await s.commit()


async def _set_org_group(group_id: str | None) -> None:
    async with SessionLocal() as s:
        cfg = await s.get(AppConfig, 1)
        if cfg is None:
            cfg = AppConfig(id=1)
            s.add(cfg)
        cfg.org_view_group_id = group_id
        await s.commit()


def _viewer_headers(upn: str = MY_UPN, oid: str = MY_OID) -> dict[str, str]:
    token = create_access_token(upn, "viewer", oid=oid, upn=upn)
    return {"Authorization": f"Bearer {token}"}


async def _admin_headers(client) -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(
            AppUser(username="admin", password_hash=hash_password("pw"), role="admin")
        )
        await s.commit()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# Personal view
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_personal_summary_counts_only_my_own_agents(client):
    await _seed_agents()
    r = await client.get("/reports/me/summary", headers=_viewer_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    # Two agents of mine, five of theirs. Anything higher is a leak.
    assert body["agents"] == MINE
    assert body["open_findings"] == MINE
    assert body["avg_score"] == 85
    assert body["has_data"] is True


@pytest.mark.asyncio
async def test_personal_view_cannot_be_pointed_at_someone_else(client):
    """The caller is taken from the token, so a spoofed id changes nothing."""
    await _seed_agents()
    r = await client.get(
        f"/reports/me/agents?upn={THEIR_UPN}&created_by_upn={THEIR_UPN}"
        f"&user={THEIR_UPN}",
        headers=_viewer_headers(),
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == MINE
    assert all(row["bot_id"].startswith("mine-") for row in rows)
    assert THEIR_UPN not in r.text
    assert "theirs-bot" not in r.text


@pytest.mark.asyncio
async def test_personal_agent_detail_refuses_other_peoples_agents(client):
    """Bot ids name an agent, not a user — ownership is still checked."""
    await _seed_agents()
    headers = _viewer_headers()
    mine = await client.get("/reports/me/agents/mine-bot-0", headers=headers)
    assert mine.status_code == 200
    assert mine.json()["agent_name"] == "mine 0"

    theirs = await client.get("/reports/me/agents/theirs-bot-0", headers=headers)
    assert theirs.status_code == 404

    history = await client.get(
        "/reports/me/agents/theirs-bot-0/history", headers=headers
    )
    assert history.status_code == 404


@pytest.mark.asyncio
async def test_personal_view_is_absent_without_an_entra_identity(client):
    """The password admin has no UPN, so there is nothing to show them."""
    headers = await _admin_headers(client)
    r = await client.get("/reports/me/summary", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_personal_view_is_empty_rather_than_broken_without_data(client):
    """Someone who has created no agents gets an empty view, not an error."""
    await _seed_agents()
    r = await client.get(
        "/reports/me/summary",
        headers=_viewer_headers(upn="new@contoso.com", oid="dddddddd-dddd-dddd-dddd-dddddddddddd"),
    )
    assert r.status_code == 200
    assert r.json()["agents"] == 0
    assert r.json()["has_data"] is False


@pytest.mark.asyncio
async def test_personal_view_requires_authentication(client):
    r = await client.get("/reports/me/summary")
    assert r.status_code in (401, 403)


# --------------------------------------------------------------------------- #
# Organisation-view gate
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_org_view_open_when_no_group_configured(client):
    """Upgrades must not silently lock existing viewers out."""
    await _seed_agents()
    await _set_org_group(None)
    r = await client.get("/reports/all-agents", headers=_viewer_headers())
    assert r.status_code == 200, r.text
    assert len(r.json()) == MINE + THEIRS


@pytest.mark.asyncio
async def test_org_view_denied_to_non_members(client):
    await _seed_agents()
    await _set_org_group(GROUP)
    r = await client.get("/reports/all-agents", headers=_viewer_headers())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_org_view_allowed_for_group_members(client, monkeypatch):
    await _seed_agents()
    await _set_org_group(GROUP)

    import api.oidc as oidc

    async def _member(principal, group_id, session):
        return group_id == GROUP

    monkeypatch.setattr(oidc, "is_group_member", _member)
    r = await client.get("/reports/all-agents", headers=_viewer_headers())
    assert r.status_code == 200
    assert len(r.json()) == MINE + THEIRS


@pytest.mark.asyncio
async def test_admin_bypasses_the_org_group(client):
    await _seed_agents()
    await _set_org_group(GROUP)
    headers = await _admin_headers(client)
    r = await client.get("/reports/all-agents", headers=headers)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_personal_view_survives_the_org_gate(client):
    """Losing org access must not cost someone their own data."""
    await _seed_agents()
    await _set_org_group(GROUP)
    headers = _viewer_headers()
    assert (
        await client.get("/reports/all-agents", headers=headers)
    ).status_code == 403
    r = await client.get("/reports/me/summary", headers=headers)
    assert r.status_code == 200
    assert r.json()["agents"] == MINE


@pytest.mark.asyncio
async def test_auth_me_advertises_capabilities(client):
    await _set_org_group(GROUP)
    r = await client.get("/auth/me", headers=_viewer_headers())
    body = r.json()
    assert body["has_personal_view"] is True
    assert body["can_view_org"] is False


@pytest.mark.asyncio
async def test_shared_lookups_stay_open_to_everyone(client):
    """Freshness and About sit outside the org gate — everyone needs them."""
    await _set_org_group(GROUP)
    headers = _viewer_headers()
    assert (await client.get("/reports/freshness", headers=headers)).status_code == 200
    assert (await client.get("/reports/about", headers=headers)).status_code == 200
