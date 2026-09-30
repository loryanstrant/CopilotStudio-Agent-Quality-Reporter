"""The quality timeline, the movers list, and the run log.

Two pages read ``scans`` for different questions and must not be confused: the
History timeline asks "is quality moving", Scan history asks "did it run". The
assertions below pin the parts that are easy to get quietly wrong — the spread
band, a mover compared against the last time it was actually measured, and the
three spellings of "succeeded".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api.metrics import (
    JOB_KIND_LABELS,
    biggest_movers,
    quality_timeline,
    scan_history,
)
from shared.db import SessionLocal
from shared.models import Agent, AgentScore, Environment, JobRun, Scan

NOW = datetime(2026, 9, 20, 3, 0, tzinfo=timezone.utc)


async def scan_with(session, env_id: int | None, *, at: datetime, scores: dict[str, int]):
    """One complete scan holding a score per bot id."""
    scan = Scan(
        environment_id=env_id,
        source="demo",
        trigger="scheduled",
        status="complete",
        started_at=at,
        finished_at=at + timedelta(minutes=2),
        agent_count=len(scores),
        agents_done=len(scores),
    )
    session.add(scan)
    await session.flush()
    for bot, score in scores.items():
        session.add(
            AgentScore(
                scan_id=scan.id,
                environment_id=env_id,
                bot_id=bot,
                agent_name=f"Agent {bot}",
                score=score,
                grade="C",
                captured_at=at,
            )
        )
    return scan


@pytest.fixture
async def tenant():
    """Two environments, two creators, three scans with movement in them."""
    async with SessionLocal() as session:
        first = Environment(display_name="Contoso")
        second = Environment(display_name="Contoso — UAT")
        session.add_all([first, second])
        await session.flush()
        session.add_all(
            [
                Agent(bot_id="a", display_name="Agent a", created_by_upn="ava@x.com"),
                Agent(bot_id="b", display_name="Agent b", created_by_upn="ava@x.com"),
                Agent(bot_id="c", display_name="Agent c", created_by_upn="noah@x.com"),
            ]
        )
        await scan_with(
            session, first.id, at=NOW - timedelta(days=2), scores={"a": 40, "b": 90, "c": 50}
        )
        # Agent b is missing from this scan, so the next one must compare it with
        # the measurement two scans ago rather than dropping it.
        await scan_with(session, first.id, at=NOW - timedelta(days=1), scores={"a": 60, "c": 50})
        await scan_with(
            session, first.id, at=NOW, scores={"a": 70, "b": 55, "c": 50}
        )
        await scan_with(session, second.id, at=NOW, scores={"a": 10})
        await session.commit()
        return {"first": first.id, "second": second.id}


@pytest.mark.asyncio
async def test_the_band_shows_spread_beside_the_average(tenant):
    """A rising average hiding one collapsing agent is the case this exists for."""
    async with SessionLocal() as session:
        points = await quality_timeline(session, environment_id=tenant["first"])

    assert [p["avg_score"] for p in points] == [60, 55, 58]
    assert points[0]["min_score"] == 40 and points[0]["max_score"] == 90
    assert points[-1]["min_score"] == 50 and points[-1]["max_score"] == 70
    # One point per scan. A day with no scan is no observation, not a zero, so
    # nothing is filled in between them.
    assert len(points) == 3
    assert points[1]["agents"] == 2


@pytest.mark.asyncio
async def test_the_timeline_responds_to_all_three_filters(tenant):
    async with SessionLocal() as session:
        by_env = await quality_timeline(session, environment_id=tenant["second"])
        by_creator = await quality_timeline(session, creator_upn="NOAH@x.com")
        by_agent = await quality_timeline(session, bot_id="b")

    assert [p["avg_score"] for p in by_env] == [10]
    # Creator matching is case-insensitive: Dataverse and Entra disagree.
    assert {p["avg_score"] for p in by_creator} == {50}
    assert [p["avg_score"] for p in by_agent] == [90, 55]


@pytest.mark.asyncio
async def test_movers_carry_direction_numbers_and_grades(tenant):
    async with SessionLocal() as session:
        result = await biggest_movers(session, environment_id=tenant["first"])

    movers = {m["bot_id"]: m for m in result["movers"]}
    # Agent b skipped a scan; it is still compared with its last real score.
    assert movers["b"]["from_score"] == 90
    assert movers["b"]["to_score"] == 55
    assert movers["b"]["delta"] == -35
    assert movers["b"]["direction"] == "down"
    assert movers["b"]["from_grade"] and movers["b"]["to_grade"]
    assert movers["a"]["direction"] == "up"
    # Biggest absolute movement first, and an agent that did not move is absent.
    assert [m["bot_id"] for m in result["movers"]] == ["b", "a"]


@pytest.mark.asyncio
async def test_run_log_merges_scans_with_job_runs(tenant):
    """This app's run log has always been ``scans``; ``job_runs`` is new here."""
    async with SessionLocal() as session:
        session.add(
            JobRun(
                job_name="creators",
                started_at=NOW - timedelta(hours=1),
                finished_at=NOW - timedelta(hours=1) + timedelta(seconds=6),
                status="success",
                stats={"creators": 14, "resolved": 13, "unresolved": 1},
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        rows = await scan_history(session)

    kinds = [r["kind"] for r in rows]
    assert "Creator directory" in kinds
    assert JOB_KIND_LABELS["creators"] == "Creator directory"
    # Demo scans are named plainly, so seeded numbers are never mistaken for real.
    assert "Demo data" in kinds
    # Newest first, across both sources.
    stamps = [r["started_at"] for r in rows if r["started_at"]]
    assert stamps == sorted(stamps, reverse=True)
    directory_row = next(r for r in rows if r["kind"] == "Creator directory")
    assert directory_row["state"] == "succeeded"
    assert directory_row["duration_seconds"] == 6


@pytest.mark.asyncio
async def test_every_spelling_of_succeeded_reads_as_one_state():
    """This repo writes ``complete``; its siblings write ``success``/``completed``."""
    async with SessionLocal() as session:
        env = Environment(display_name="Contoso")
        session.add(env)
        await session.flush()
        for status in ("complete", "completed", "success"):
            session.add(
                Scan(
                    environment_id=env.id,
                    source="dataverse",
                    trigger="manual",
                    status=status,
                    started_at=NOW,
                    finished_at=NOW + timedelta(seconds=30),
                    agent_count=3,
                    agents_done=3,
                )
            )
        await session.commit()

    async with SessionLocal() as session:
        rows = await scan_history(session)
    assert {r["state"] for r in rows} == {"succeeded"}
    assert {r["kind"] for r in rows} == {"Manual · Dataverse"}


@pytest.mark.asyncio
async def test_an_unrecognised_kind_renders_raw_rather_than_vanishing():
    """A run that happened and is not listed is worse than an awkward label."""
    async with SessionLocal() as session:
        session.add(
            JobRun(
                job_name="csv-cowork-usage",
                started_at=NOW,
                finished_at=NOW,
                status="success",
                stats={},
            )
        )
        session.add(
            JobRun(
                job_name="something-nobody-mapped",
                started_at=NOW - timedelta(minutes=5),
                finished_at=NOW,
                status="weird-status",
                stats={},
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        rows = await scan_history(session)

    kinds = {r["kind"] for r in rows}
    # A sibling's value still reads, because the mapping is a superset.
    assert "Cowork usage import" in kinds
    # And an unmapped one survives as itself, status included.
    assert "something-nobody-mapped" in kinds
    unmapped = next(r for r in rows if r["raw_kind"] == "something-nobody-mapped")
    assert unmapped["state"] == "weird-status"


@pytest.mark.asyncio
async def test_a_failed_scan_shows_its_reason_and_a_partial_scan_is_flagged():
    async with SessionLocal() as session:
        env = Environment(display_name="Contoso")
        session.add(env)
        await session.flush()
        session.add(
            Scan(
                environment_id=env.id,
                source="dataverse",
                trigger="scheduled",
                status="failed",
                started_at=NOW,
                finished_at=NOW + timedelta(seconds=41),
                agent_count=0,
                agents_done=0,
                detail="Dataverse returned 401 Unauthorized.",
            )
        )
        session.add(
            Scan(
                environment_id=env.id,
                source="dataverse",
                trigger="manual",
                status="complete",
                started_at=NOW - timedelta(hours=2),
                finished_at=NOW - timedelta(hours=1),
                agent_count=12,
                agents_done=4,
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        rows = await scan_history(session)

    failed = next(r for r in rows if r["state"] == "failed")
    assert failed["error"] == "Dataverse returned 401 Unauthorized."
    assert failed["environment"] == "Contoso"

    partial = next(r for r in rows if r["agents_scored"] == 4)
    assert partial["partial"] is True, "a part-finished scan was invisible before"
    assert partial["agents_found"] == 12
