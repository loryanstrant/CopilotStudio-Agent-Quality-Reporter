"""Aggregations shared by more than one route.

Three things live here rather than in ``api/routers/reports.py``, because each is
read by two callers and duplicating any of them would let two pages disagree
about the same number:

* :func:`creator_rollup` — agents and average score per creator. The Agent
  creators listing and the personal comparison both read it.
* :func:`peer_comparison` — you, your team, your organisation.
* :func:`quality_timeline` / :func:`biggest_movers` — the History timeline.
* :func:`scan_history` — the run log, which merges two tables.

The vocabulary constants at the top are the single place the suite's messy
``job_name`` and status values are mapped to something readable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Agent, AgentCreator, AgentScore, Environment, JobRun, Scan

# --------------------------------------------------------------------------- #
# Vocabulary
#
# The suite's run-log vocabulary is not a shared enum, and pretending otherwise
# was the first thing this feature got wrong. Each app enumerates what **it**
# writes, and also carries its siblings' values so a row written under another
# schema still reads. An unmapped kind renders as its raw value rather than
# vanishing: a run that happened and is not listed is worse than one labelled
# awkwardly.
# --------------------------------------------------------------------------- #

# What this repo actually writes. Verified by grep, not assumed: ``scans`` rows
# carry trigger+source (see scan_history below) and job_runs rows currently come
# from exactly one place, the creator directory sync.
JOB_KIND_LABELS = {
    # Ours.
    "creators": "Creator directory",
    "manual": "Manual",
    "scheduled": "Scheduled",
    # The siblings', so a row written by another app's schema still reads.
    "daily": "Scheduled",
    "users": "User sync",
    "backfill": "Historical backfill",
    "csv-cowork-usage": "Cowork usage import",
    "csv-credit-consumption": "Credit consumption import",
}

# Seven status spellings exist across the suite, and three of them mean the same
# thing. This app writes ``complete``; Usage Reporter writes ``success``; Cowork
# writes ``completed``. The display layer absorbs it and this is the one place
# the mapping is decided.
RUN_STATUS_STATE = {
    "complete": "succeeded",
    "completed": "succeeded",
    "success": "succeeded",
    "running": "running",
    "preparing": "running",
    "failed": "failed",
    "cancelled": "cancelled",
}

# What a scan read, spelled for people rather than for the schema.
SCAN_SOURCE_LABELS = {
    "dataverse": "Dataverse",
    "zip": "Solution ZIP",
    "demo": "Demo data",
}
SCAN_TRIGGER_LABELS = {"manual": "Manual", "scheduled": "Scheduled"}

# A team series is drawn only when the grouping holds at least this many people
# besides the viewer. Below it, the team average plus the viewer's own figure
# gives away an individual's number — exactly at n=1, and closely enough to
# matter at 2 to 4. This is a disclosure rule, not a presentation preference;
# see docs/specs/comparisons-and-timelines.md.
MIN_TEAM_PEERS = 5


# --------------------------------------------------------------------------- #
# Per-creator measures
# --------------------------------------------------------------------------- #
async def latest_score_by_bot(session: AsyncSession) -> dict[str, AgentScore]:
    """Each agent's most recent scored appearance, keyed by bot id.

    Two queries regardless of how many agents exist: group to find each bot's
    newest capture, then join back for the whole row.
    """
    newest = (
        select(AgentScore.bot_id, func.max(AgentScore.captured_at).label("ts"))
        .where(AgentScore.bot_id.isnot(None))
        .group_by(AgentScore.bot_id)
        .subquery()
    )
    latest: dict[str, AgentScore] = {}
    for row in (
        await session.execute(
            select(AgentScore).join(
                newest,
                and_(
                    AgentScore.bot_id == newest.c.bot_id,
                    AgentScore.captured_at == newest.c.ts,
                ),
            )
        )
    ).scalars().all():
        # Two scans can share a timestamp; first one wins.
        latest.setdefault(str(row.bot_id), row)
    return latest


async def directory_by_upn(session: AsyncSession) -> dict[str, AgentCreator]:
    """The creator directory, keyed by lower-cased UPN."""
    rows = (await session.execute(select(AgentCreator))).scalars().all()
    return {r.upn: r for r in rows}


async def creator_rollup(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """Agents made and average score, per creator, keyed by lower-cased UPN.

    ``avg_score`` is the mean over that person's agents' most recent scored
    appearance, so it reflects the current state of their agents rather than
    whichever scan happened to run last in their environment. It is ``None``
    when none of their agents has ever been scored — which is not zero, and must
    not average as zero.
    """
    agents = (
        await session.execute(select(Agent).where(Agent.created_by_upn.isnot(None)))
    ).scalars().all()
    latest = await latest_score_by_bot(session)

    out: dict[str, dict[str, Any]] = {}
    for agent in agents:
        key = (agent.created_by_upn or "").lower()
        if not key:
            continue
        row = out.setdefault(
            key,
            {
                "upn": agent.created_by_upn,
                "created_by_name": agent.created_by_name,
                "agents": 0,
                "scores": [],
            },
        )
        row["created_by_name"] = row["created_by_name"] or agent.created_by_name
        row["agents"] += 1
        score_row = latest.get(str(agent.bot_id)) if agent.bot_id else None
        if score_row is not None and score_row.score is not None:
            row["scores"].append(int(score_row.score))

    for row in out.values():
        scores = row["scores"]
        row["avg_score"] = round(sum(scores) / len(scores)) if scores else None
    return out


def _department_of(creator: AgentCreator | None) -> str | None:
    """A creator's department, lower-cased for comparison, or ``None``.

    Nothing is ever compared against ``None``, so a tenant that leaves
    ``department`` blank cannot accidentally produce one enormous team of
    everybody-with-no-department.
    """
    if creator is None:
        return None
    value = (creator.department or "").strip()
    return value.lower() or None


def _percentile(value: float | None, population: list[float]) -> int | None:
    """Where ``value`` sits in ``population`` — the share it is at least equal to."""
    if value is None or not population:
        return None
    at_or_below = sum(1 for p in population if p <= value)
    return round(at_or_below / len(population) * 100)


def _mean(values: list[float]) -> int | None:
    return round(sum(values) / len(values)) if values else None


async def _observed_period(session: AsyncSession) -> tuple[datetime | None, datetime | None]:
    """The span the data actually covers.

    The personal page has no date filter, so "the selected period" would be a
    phrase with nothing behind it. The honest answer is the window the figures
    were computed over: from the oldest agent's creation to the most recent
    score captured.
    """
    first = await session.scalar(select(func.min(Agent.created_on)))
    last = await session.scalar(select(func.max(AgentScore.captured_at)))
    return first, last


async def peer_comparison(session: AsyncSession, *, upn: str) -> dict[str, Any]:
    """This person, their team and the organisation, on the same two measures.

    Aggregates only — a mean per group, never a list of people. The team is the
    viewer's department, falling back to everyone sharing their manager, and is
    **omitted entirely** below :data:`MIN_TEAM_PEERS` rather than drawn from a
    group small enough to identify somebody.

    ``team_omitted_reason`` distinguishes the four ways a team can be missing,
    because they are not the same thing and the wording on screen must not imply
    a problem with the reader's directory record when there is none:

    ``not_a_creator``
        The viewer has created no agents, so there is no directory row for them
        — the lookup is scoped to creators by design.
    ``directory_unresolved``
        They are a creator, but Graph has not resolved them (no consent yet, a
        lookup that failed, or an address with no directory record).
    ``unknown_team``
        Resolved, but the tenant populates neither department nor manager.
    ``too_small``
        A team was found and is being withheld to avoid identifying someone.
    """
    key = (upn or "").lower()
    rollup = await creator_rollup(session)
    directory = await directory_by_upn(session)

    me = rollup.get(key)
    mine = {
        "agents": int((me or {}).get("agents") or 0),
        "avg_score": (me or {}).get("avg_score"),
    }

    others = [r for k, r in rollup.items() if k != key]
    org_scores = [float(r["avg_score"]) for r in others if r["avg_score"] is not None]
    org_agents = [float(r["agents"]) for r in others]

    peers: list[dict[str, Any]] = []
    team_label: str | None = None
    reason: str | None = None
    my_directory = directory.get(key)

    if me is None:
        reason = "not_a_creator"
    elif my_directory is None or not my_directory.resolved:
        reason = "directory_unresolved"
    else:
        department = (my_directory.department or "").strip()
        if department:
            peers = [
                r
                for k, r in rollup.items()
                if k != key
                and _department_of(directory.get(k)) == department.lower()
            ]
            team_label = department
        if len(peers) < MIN_TEAM_PEERS and my_directory.manager_id:
            # Falling back does not relax the threshold: a department of one
            # becoming a manager group of two is still a group of two.
            by_manager = [
                r
                for k, r in rollup.items()
                if k != key
                and directory.get(k) is not None
                and directory.get(k).manager_id == my_directory.manager_id
            ]
            if len(by_manager) > len(peers):
                peers = by_manager
                team_label = (
                    f"{my_directory.manager_name}'s team"
                    if my_directory.manager_name
                    else "your manager's team"
                )
        if not peers and not team_label:
            reason = "unknown_team"
        elif len(peers) < MIN_TEAM_PEERS:
            reason = "too_small"

    period_from, period_to = await _observed_period(session)
    result: dict[str, Any] = {
        "period_from": period_from.isoformat() if period_from else None,
        "period_to": period_to.isoformat() if period_to else None,
        "mine": mine,
        "organisation": {
            "agents": _mean(org_agents) or 0,
            "avg_score": _mean(org_scores),
        },
        "organisation_size": len(others),
        "percentile": {
            "agents": _percentile(float(mine["agents"]), org_agents),
            "avg_score": _percentile(
                float(mine["avg_score"]) if mine["avg_score"] is not None else None,
                org_scores,
            ),
        },
        "team": None,
        "team_label": None,
        "team_size": len(peers),
        "team_omitted_reason": reason,
    }

    if len(peers) >= MIN_TEAM_PEERS:
        result["team"] = {
            "agents": _mean([float(r["agents"]) for r in peers]) or 0,
            "avg_score": _mean(
                [float(r["avg_score"]) for r in peers if r["avg_score"] is not None]
            ),
        }
        result["team_label"] = team_label
        result["team_omitted_reason"] = None
    return result


# --------------------------------------------------------------------------- #
# Quality over time
# --------------------------------------------------------------------------- #
async def _filtered_scores(
    session: AsyncSession,
    *,
    environment_id: int | None,
    creator_upn: str | None,
    bot_id: str | None,
) -> list[tuple[AgentScore, str | None]]:
    """Per-agent scores matching the filters, with each agent's creator UPN."""
    query = (
        select(AgentScore, Agent.created_by_upn)
        .outerjoin(Agent, Agent.bot_id == AgentScore.bot_id)
        .join(Scan, Scan.id == AgentScore.scan_id)
        .where(AgentScore.score.isnot(None), Scan.status == "complete")
        .order_by(AgentScore.captured_at)
    )
    if environment_id is not None:
        query = query.where(AgentScore.environment_id == environment_id)
    if bot_id:
        query = query.where(AgentScore.bot_id == bot_id)
    if creator_upn:
        query = query.where(func.lower(Agent.created_by_upn) == creator_upn.lower())
    return list((await session.execute(query)).all())


async def quality_timeline(
    session: AsyncSession,
    *,
    environment_id: int | None = None,
    creator_upn: str | None = None,
    bot_id: str | None = None,
) -> list[dict[str, Any]]:
    """Average score per scan, with the best and worst agent in that scan.

    The band between ``min`` and ``max`` is the point of this shape: an average
    that climbs while one agent collapses looks like progress on a line chart
    and looks like trouble as soon as the spread is drawn behind it.

    One point per scan, not per calendar day. A day with no scan is **not** a
    zero — it is no observation, and filling it would assert a score that was
    never measured.
    """
    rows = await _filtered_scores(
        session,
        environment_id=environment_id,
        creator_upn=creator_upn,
        bot_id=bot_id,
    )
    buckets: dict[int, dict[str, Any]] = {}
    for score_row, _upn in rows:
        b = buckets.setdefault(
            score_row.scan_id,
            {
                "scan_id": score_row.scan_id,
                "captured_at": score_row.captured_at,
                "scores": [],
            },
        )
        b["scores"].append(int(score_row.score or 0))
        # The earliest capture in the scan dates the point, so a long scan is
        # plotted where it started rather than where it happened to finish.
        if score_row.captured_at and score_row.captured_at < b["captured_at"]:
            b["captured_at"] = score_row.captured_at

    out: list[dict[str, Any]] = []
    for bucket in sorted(buckets.values(), key=lambda b: (b["captured_at"] or datetime.min)):
        scores = bucket["scores"]
        out.append(
            {
                "scan_id": bucket["scan_id"],
                "captured_at": bucket["captured_at"].isoformat()
                if bucket["captured_at"]
                else None,
                "agents": len(scores),
                "avg_score": round(sum(scores) / len(scores)),
                "min_score": min(scores),
                "max_score": max(scores),
            }
        )
    return out


def _grade_for(score: int) -> str:
    """Mirrors engine.static_rules.grade_for_score, for a score we already hold."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


async def biggest_movers(
    session: AsyncSession,
    *,
    environment_id: int | None = None,
    creator_upn: str | None = None,
    bot_id: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """Which agents moved most between the last two scans in the filtered set.

    Compares each agent's score in the newest scan with its score in the
    previous scan it appeared in — not with the previous scan overall, so an
    agent that was skipped by one run is still compared with the last real
    measurement of it rather than dropping out of the list.
    """
    rows = await _filtered_scores(
        session,
        environment_id=environment_id,
        creator_upn=creator_upn,
        bot_id=bot_id,
    )
    if not rows:
        return {"from_at": None, "to_at": None, "movers": []}

    # Each agent's scores oldest-first (the query is ordered by capture).
    history: dict[str, list[AgentScore]] = {}
    for score_row, _upn in rows:
        history.setdefault(str(score_row.bot_id), []).append(score_row)

    latest_at = max(r.captured_at for r, _ in rows if r.captured_at)
    movers: list[dict[str, Any]] = []
    previous_at: datetime | None = None
    for bot, scores in history.items():
        if len(scores) < 2:
            continue
        current, prior = scores[-1], scores[-2]
        delta = int(current.score or 0) - int(prior.score or 0)
        if delta == 0:
            continue
        if prior.captured_at and (previous_at is None or prior.captured_at > previous_at):
            previous_at = prior.captured_at
        movers.append(
            {
                "bot_id": bot,
                "agent_name": current.agent_name,
                "from_score": int(prior.score or 0),
                "to_score": int(current.score or 0),
                "delta": delta,
                # Direction as a word as well as the arrow the UI draws, so the
                # row reads without shape or colour at all.
                "direction": "up" if delta > 0 else "down",
                "from_grade": prior.grade or _grade_for(int(prior.score or 0)),
                "to_grade": current.grade or _grade_for(int(current.score or 0)),
                "captured_at": current.captured_at.isoformat()
                if current.captured_at
                else None,
            }
        )
    movers.sort(key=lambda m: (-abs(m["delta"]), m["agent_name"] or ""))
    return {
        "from_at": previous_at.isoformat() if previous_at else None,
        "to_at": latest_at.isoformat() if latest_at else None,
        "movers": movers[:limit],
    }


# --------------------------------------------------------------------------- #
# Scan history — the run log
# --------------------------------------------------------------------------- #
def _duration(started: datetime | None, finished: datetime | None) -> int | None:
    if not started or not finished:
        return None
    return max(0, int((finished - started).total_seconds()))


async def scan_history(
    session: AsyncSession, *, limit: int = 200
) -> list[dict[str, Any]]:
    """Every run this deployment has recorded, newest first.

    Reads **two** tables, and that is deliberate. In this app the run log has
    always been ``scans`` — ``worker/scan.py`` has written it since the first
    release — while ``job_runs`` was declared and never written until the creator
    directory sync arrived. A page called Scan history that listed an empty
    ``job_runs`` while dozens of real scans sat in another table would be the
    worst of both. So both are listed, sorted together.

    This is the run log. The History page is the quality trend. Both read
    ``scans``, for different questions: "did it run?" against "is it getting
    better?".
    """
    env_names = {
        e.id: e.display_name
        for e in (await session.execute(select(Environment))).scalars().all()
    }

    scans = (
        await session.execute(select(Scan).order_by(Scan.started_at.desc()).limit(limit))
    ).scalars().all()

    out: list[dict[str, Any]] = []
    for s in scans:
        source = (s.source or "").lower()
        trigger = (s.trigger or "").lower()
        if source == "demo":
            # Named plainly so nobody mistakes seeded numbers for real ones.
            kind = SCAN_SOURCE_LABELS["demo"]
        else:
            kind = " · ".join(
                part
                for part in (
                    SCAN_TRIGGER_LABELS.get(trigger, s.trigger or ""),
                    SCAN_SOURCE_LABELS.get(source, s.source or ""),
                )
                if part
            )
        wrote: dict[str, Any] = {"agents": s.agent_count}
        if s.score is not None:
            wrote["score"] = s.score
        if s.grade:
            wrote["grade"] = s.grade
        # A finished scan that scored fewer agents than it found is a partial
        # scan, and until now that was invisible anywhere in the UI.
        partial = (
            RUN_STATUS_STATE.get((s.status or "").lower()) not in (None, "running")
            and s.agents_done < s.agent_count
        )
        out.append(
            {
                "id": f"scan-{s.id}",
                "scan_id": s.id,
                "kind": kind or "Scan",
                "raw_kind": f"{s.trigger}/{s.source}",
                "environment": env_names.get(s.environment_id)
                if s.environment_id is not None
                else None,
                "state": RUN_STATUS_STATE.get((s.status or "").lower(), s.status),
                "raw_status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                "duration_seconds": _duration(s.started_at, s.finished_at),
                "agents_found": s.agent_count,
                "agents_scored": s.agents_done,
                "partial": partial,
                "score": s.score,
                "grade": s.grade,
                "engine_version": s.engine_version,
                # A scan keeps its failure reason in its own column rather than
                # in a stats blob, so it is read from there.
                "error": s.detail,
                "wrote": wrote,
            }
        )

    runs = (
        await session.execute(
            select(JobRun).order_by(JobRun.started_at.desc()).limit(limit)
        )
    ).scalars().all()
    for r in runs:
        stats = r.stats if isinstance(r.stats, dict) else {}
        out.append(
            {
                "id": f"job-{r.id}",
                "scan_id": None,
                "kind": JOB_KIND_LABELS.get(r.job_name, r.job_name),
                "raw_kind": r.job_name,
                "environment": None,
                "state": RUN_STATUS_STATE.get((r.status or "").lower(), r.status),
                "raw_status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "duration_seconds": _duration(r.started_at, r.finished_at),
                "agents_found": None,
                "agents_scored": None,
                "partial": False,
                "score": None,
                "grade": None,
                "engine_version": None,
                "error": stats.get("error"),
                "wrote": {k: v for k, v in stats.items() if k != "error"},
            }
        )

    out.sort(key=lambda r: (r["started_at"] or ""), reverse=True)
    return out[:limit]
