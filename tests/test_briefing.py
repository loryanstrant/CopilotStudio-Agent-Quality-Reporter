"""The executive briefing.

The claims worth testing here are about honesty rather than presentation:

- the comparison is one scan per environment per period, not every scan in the
  window, or an environment scanned nightly outweighs one scanned weekly;
- both periods are measured back from the most recent scan rather than from
  today, so a fortnight of nobody scanning does not read as a collapse;
- it is org-gated, and it degrades to an explicit "no data" rather than to
  zeroes that look like a real answer.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api.auth import create_access_token
from shared.db import SessionLocal
from shared.models import AgentScore, AppUser, Environment, Finding, Scan
from shared.security import hash_password

NOW = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


async def _admin_headers() -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    return {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


async def _scan(
    session, env_id: int, started: datetime, scores: list[int], fails: list[str]
) -> Scan:
    scan = Scan(
        environment_id=env_id,
        source="demo",
        status="complete",
        started_at=started,
        finished_at=started + timedelta(minutes=2),
        agent_count=len(scores),
    )
    session.add(scan)
    await session.flush()
    for i, score in enumerate(scores):
        session.add(
            AgentScore(
                scan_id=scan.id,
                environment_id=env_id,
                bot_id=f"bot-{env_id}-{i}",
                agent_name=f"Agent {env_id}-{i}",
                score=score,
                grade="A" if score >= 90 else "C" if score >= 60 else "F",
                captured_at=started,
            )
        )
    for j, severity in enumerate(fails):
        session.add(
            Finding(
                scan_id=scan.id,
                rule_id=f"RULE-{j}",
                name=f"Rule {j}",
                severity=severity,
                status="fail",
                agent_name=f"Agent {env_id}-0",
            )
        )
    return scan


async def _seed_two_periods() -> None:
    """One environment, an old scan and a recent one, 40 days apart."""
    async with SessionLocal() as s:
        env = Environment(display_name="Contoso", enabled=True)
        s.add(env)
        await s.flush()
        # Previous period: 40 days back, poor scores, three failures.
        await _scan(s, env.id, NOW - timedelta(days=40), [40, 50], ["blocker", "major", "minor"])
        # Current period: today, better scores, one failure.
        await _scan(s, env.id, NOW, [90, 70], ["minor"])
        await s.commit()


@pytest.mark.asyncio
async def test_briefing_compares_this_period_with_the_one_before(client):
    await _seed_two_periods()
    b = (await client.get("/reports/briefing", headers=await _admin_headers())).json()

    assert b["has_data"] is True
    assert b["current"]["agents"] == 2
    assert b["current"]["avg_score"] == 80
    assert b["previous"]["avg_score"] == 45
    assert b["current"]["open_findings"] == 1
    assert b["previous"]["open_findings"] == 3


@pytest.mark.asyncio
async def test_periods_are_measured_from_the_last_scan_not_from_today(client):
    """Everything here is historic. Measured from today both periods would be
    empty, and the briefing would report a collapse that never happened."""
    async with SessionLocal() as s:
        env = Environment(display_name="Contoso", enabled=True)
        s.add(env)
        await s.flush()
        await _scan(s, env.id, NOW - timedelta(days=400), [60], [])
        await _scan(s, env.id, NOW - timedelta(days=360), [80], [])
        await s.commit()

    b = (await client.get("/reports/briefing", headers=await _admin_headers())).json()
    assert b["current"]["avg_score"] == 80
    assert b["previous"]["avg_score"] == 60


@pytest.mark.asyncio
async def test_only_the_latest_scan_per_environment_counts(client):
    """Three scans of the same two agents in one period is still two agents."""
    async with SessionLocal() as s:
        env = Environment(display_name="Contoso", enabled=True)
        s.add(env)
        await s.flush()
        for day in (3, 2, 1):
            await _scan(s, env.id, NOW - timedelta(days=day), [70, 70], [])
        await s.commit()

    b = (await client.get("/reports/briefing", headers=await _admin_headers())).json()
    assert b["current"]["agents"] == 2
    assert b["current"]["environments"] == 1


@pytest.mark.asyncio
async def test_grade_mix_and_severities_are_broken_out(client):
    await _seed_two_periods()
    b = (await client.get("/reports/briefing", headers=await _admin_headers())).json()
    assert b["current"]["grades"] == {"A": 1, "B": 0, "C": 1, "D": 0, "F": 0}
    assert b["current"]["findings_by_severity"]["minor"] == 1
    assert b["current"]["findings_by_severity"]["blocker"] == 0


@pytest.mark.asyncio
async def test_top_rules_names_what_fails_most(client):
    await _seed_two_periods()
    b = (await client.get("/reports/briefing", headers=await _admin_headers())).json()
    assert b["top_rules"]
    assert b["top_rules"][0]["agents"] >= 1


@pytest.mark.asyncio
async def test_no_data_says_so_rather_than_reporting_zeroes(client):
    """Zeroes look like a real answer. An empty tenant must say it is empty."""
    b = (await client.get("/reports/briefing", headers=await _admin_headers())).json()
    assert b["has_data"] is False
    assert b["period_end"] is None


@pytest.mark.asyncio
async def test_briefing_is_organisation_gated(client):
    """It names agents and scores across every environment, so it is not open
    to any signed-in user."""
    async with SessionLocal() as s:
        from shared.models import AppConfig

        s.add(AppConfig(id=1, org_view_group_id="gggggggg-gggg-gggg-gggg-gggggggggggg"))
        await s.commit()

    token = create_access_token(
        "ada@contoso.com", "viewer", oid="oid-1", upn="ada@contoso.com"
    )
    r = await client.get("/reports/briefing", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
