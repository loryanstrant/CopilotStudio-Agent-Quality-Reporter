"""Report routes — agent-first.

The dashboard is organised around agents: pick an environment, see every agent
with its own score/grade, click an agent for its findings + explanations + LLM
judge + telemetry, and view that agent's daily score history.

Routes are split by who may see what:

``router`` — organisation-wide data (every environment, every agent). Gated by
:func:`require_org_view`, so it needs both a valid token and membership of the
configured organisation-view group (admins always pass).

``common_router`` — data any signed-in user may see regardless of that group:
build info and data freshness.

``me_router`` — the personal view: the agents the signed-in person created.
Every route derives the person from the token, never from a client-supplied
parameter.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import (
    CurrentUser,
    get_current_user,
    personal_view_upn,
    require_org_view,
)
from shared.db import get_session
from shared.models import (
    Agent,
    AgentScore,
    Environment,
    Finding,
    JudgeResult,
    Scan,
    TelemetrySnapshot,
)

router = APIRouter(
    prefix="/reports", tags=["reports"], dependencies=[Depends(require_org_view)]
)

common_router = APIRouter(
    prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)]
)

me_router = APIRouter(prefix="/reports/me", tags=["reports", "personal"])


async def _latest_scan_per_env(session: AsyncSession) -> dict[int | None, Scan]:
    """Most recent complete scan for each real environment (demo excluded)."""
    scans = (
        await session.execute(
            select(Scan)
            .where(Scan.status == "complete", Scan.environment_id.isnot(None))
            .order_by(Scan.started_at.desc())
        )
    ).scalars().all()
    latest: dict[int | None, Scan] = {}
    for s in scans:
        if s.environment_id not in latest:
            latest[s.environment_id] = s
    return latest


@common_router.get("/about")
async def about() -> dict:
    """App version metadata for the About page (any authenticated user)."""
    from engine.loader import ENGINE_VERSION, catalogue_hash
    from shared.version import APP_VERSION, BUILD_DATE, BUILD_TIME

    return {
        "version": APP_VERSION,
        "engine_version": ENGINE_VERSION,
        "catalogue_hash": catalogue_hash(),
        "build_date": BUILD_DATE,
        "build_time": BUILD_TIME,
    }


@router.get("/environments")
async def environments(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """One card per environment that has been scanned, with a rollup + latest scan."""
    latest = await _latest_scan_per_env(session)
    env_rows = {
        e.id: e
        for e in (await session.execute(select(Environment))).scalars().all()
    }
    out = []
    for env_id, scan in latest.items():
        name = "Demo (bundled)" if env_id is None else (
            env_rows[env_id].display_name if env_id in env_rows else f"Environment {env_id}"
        )
        out.append({
            "environment_id": env_id,
            "name": name,
            "latest_scan_id": scan.id,
            "agent_count": scan.agent_count,
            "avg_score": scan.score,
            "grade": scan.grade,
            "scanned_at": scan.finished_at.isoformat() if scan.finished_at else None,
        })
    out.sort(key=lambda x: (x["environment_id"] is None, x["name"]))
    return out


@router.get("/all-agents")
async def all_agents(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Every agent across every environment's latest complete scan (default view)."""
    latest = await _latest_scan_per_env(session)
    env_rows = {
        e.id: e for e in (await session.execute(select(Environment))).scalars().all()
    }
    out: list[dict] = []
    for env_id, scan in latest.items():
        rows = (
            await session.execute(
                select(AgentScore).where(AgentScore.scan_id == scan.id)
            )
        ).scalars().all()
        env_name = env_rows[env_id].display_name if env_id in env_rows else f"Environment {env_id}"
        for a in rows:
            out.append({
                "bot_id": a.bot_id,
                "agent_name": a.agent_name,
                "solution_name": a.solution_name,
                "publish_state": a.publish_state,
                "score": a.score,
                "grade": a.grade,
                "scan_id": a.scan_id,
                "environment_id": a.environment_id,
                "environment_name": env_name,
            })
    return out


@router.get("/agents")
async def agents(scan_id: int, session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Every agent in a scan with its own score/grade (the agent list)."""
    rows = (
        await session.execute(
            select(AgentScore).where(AgentScore.scan_id == scan_id).order_by(AgentScore.score)
        )
    ).scalars().all()
    return [
        {
            "bot_id": a.bot_id,
            "agent_name": a.agent_name,
            "solution_name": a.solution_name,
            "publish_state": a.publish_state,
            "score": a.score,
            "grade": a.grade,
            "scan_id": a.scan_id,
            "environment_id": a.environment_id,
        }
        for a in rows
    ]


async def _resolve_agent_name(session: AsyncSession, scan_id: int, bot_id: str) -> str | None:
    return await session.scalar(
        select(AgentScore.agent_name).where(
            AgentScore.scan_id == scan_id, AgentScore.bot_id == bot_id
        )
    )


@router.get("/agents/{bot_id}")
async def agent_detail(
    bot_id: str, scan_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """Full scorecard for one agent within a scan."""
    score_row = await session.scalar(
        select(AgentScore).where(AgentScore.scan_id == scan_id, AgentScore.bot_id == bot_id)
    )
    if score_row is None:
        raise HTTPException(status_code=404, detail="Agent not found in this scan")
    label = score_row.agent_name

    findings = (
        await session.execute(
            select(Finding).where(Finding.scan_id == scan_id, Finding.agent_name == label)
            .order_by(Finding.id)
        )
    ).scalars().all()
    judge = await session.scalar(
        select(JudgeResult).where(JudgeResult.scan_id == scan_id, JudgeResult.agent_name == label)
    )
    telem = await session.scalar(
        select(TelemetrySnapshot).where(
            TelemetrySnapshot.scan_id == scan_id, TelemetrySnapshot.agent_name == label
        )
    )

    # Agent metadata (created/modified/creator) + environment display name.
    agent_row = None
    if bot_id:
        agent_row = await session.scalar(select(Agent).where(Agent.bot_id == bot_id))
    env_name = None
    env_guid = None
    if score_row.environment_id is not None:
        env = await session.get(Environment, score_row.environment_id)
        env_name = env.display_name if env else None
        env_guid = env.environment_guid if env else None

    # Build maker-portal / Copilot Studio deep links when we have the ids.
    agent_url = None
    solution_url = None
    if env_guid and bot_id:
        agent_url = (
            f"https://copilotstudio.microsoft.com/environments/{env_guid}"
            f"/bots/{bot_id}/overview"
        )
    if env_guid and score_row.solution_id:
        solution_url = (
            f"https://make.powerapps.com/environments/{env_guid}"
            f"/solutions/{score_row.solution_id}"
        )

    return {
        "bot_id": bot_id,
        "agent_name": label,
        "solution_name": score_row.solution_name,
        "solution_id": score_row.solution_id,
        "solution_url": solution_url,
        "agent_url": agent_url,
        "publish_state": score_row.publish_state,
        "score": score_row.score,
        "grade": score_row.grade,
        "scan_id": scan_id,
        "environment_id": score_row.environment_id,
        "environment_name": env_name,
        "environment_guid": env_guid,
        "schema_name": agent_row.schema_name if agent_row else None,
        "model_hint": agent_row.model_hint if agent_row else None,
        "created_on": agent_row.created_on.isoformat() if (agent_row and agent_row.created_on) else None,
        "modified_on": agent_row.modified_on.isoformat() if (agent_row and agent_row.modified_on) else None,
        "created_by_name": agent_row.created_by_name if agent_row else None,
        "created_by_upn": agent_row.created_by_upn if agent_row else None,
        "findings": [
            {
                "rule_id": f.rule_id, "name": f.name, "severity": f.severity, "status": f.status,
                "manual_review": f.manual_review, "weight": f.weight, "scope": f.scope,
                "details": f.details, "pp_reference": f.pp_reference,
            }
            for f in findings
        ],
        "judge": None if judge is None else {
            "skipped": judge.skipped, "error": judge.error, "clarity": judge.clarity,
            "scope_discipline": judge.scope_discipline, "persona_defined": judge.persona_defined,
            "orchestrator_pattern_detected": judge.orchestrator_pattern_detected,
            "child_pattern_detected": judge.child_pattern_detected,
            "output_format_guidance": judge.output_format_guidance,
            "top_strengths": judge.top_strengths, "top_weaknesses": judge.top_weaknesses,
            "recommended_changes": judge.recommended_changes, "summary": judge.summary,
        },
        "telemetry": None if telem is None else {
            "window_days": telem.window_days, "run_count": telem.run_count,
            "error_count": telem.error_count, "p95_latency_ms": telem.p95_latency_ms,
            "source": telem.source,
        },
    }


@router.get("/agents/{bot_id}/history")
async def agent_history(
    bot_id: str, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """Daily score history for one agent (one point per scan it appeared in)."""
    rows = (
        await session.execute(
            select(AgentScore).where(AgentScore.bot_id == bot_id).order_by(AgentScore.captured_at)
        )
    ).scalars().all()
    return [
        {
            "scan_id": a.scan_id,
            "score": a.score,
            "grade": a.grade,
            "captured_at": a.captured_at.isoformat() if a.captured_at else None,
        }
        for a in rows
    ]


@router.get("/rule-history")
async def rule_history(
    bot_id: str, rule_id: str, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """History of a single rule's outcome for one agent, across scans."""
    # Map bot_id -> agent_name via any AgentScore row, then walk findings by scan.
    label = await session.scalar(
        select(AgentScore.agent_name).where(AgentScore.bot_id == bot_id).limit(1)
    )
    if not label:
        return []
    rows = (
        await session.execute(
            select(Finding, Scan.finished_at)
            .join(Scan, Scan.id == Finding.scan_id)
            .where(Finding.agent_name == label, Finding.rule_id == rule_id)
            .order_by(Scan.started_at)
        )
    ).all()
    return [
        {
            "scan_id": f.scan_id,
            "status": f.status,
            "details": f.details,
            "captured_at": ts.isoformat() if ts else None,
        }
        for f, ts in rows
    ]


@router.get("/scan-progress")
async def scan_progress(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Any scans currently running, with a live agents-done / total counter."""
    rows = (
        await session.execute(select(Scan).where(Scan.status == "running"))
    ).scalars().all()
    return [
        {
            "scan_id": s.id,
            "environment_id": s.environment_id,
            "source": s.source,
            "agents_done": s.agents_done,
            "agent_count": s.agent_count,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        }
        for s in rows
    ]


@router.get("/scans")
async def list_scans(limit: int = 50, session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (
        await session.execute(
            select(Scan).order_by(Scan.started_at.desc()).limit(min(limit, 200))
        )
    ).scalars().all()
    env_rows = {e.id: e for e in (await session.execute(select(Environment))).scalars().all()}
    return [
        {
            "id": s.id,
            "environment": "Demo (bundled)" if s.environment_id is None else (
                env_rows[s.environment_id].display_name if s.environment_id in env_rows
                else f"Environment {s.environment_id}"
            ),
            "source": s.source,
            "trigger": s.trigger,
            "agent_count": s.agent_count,
            "avg_score": s.score,
            "grade": s.grade,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        }
        for s in rows
    ]


@common_router.get("/freshness")
async def freshness(session: AsyncSession = Depends(get_session)) -> dict:
    """Data-freshness summary for the About page.

    Counts of what has been scanned, the window covered, and the last run.
    """
    from sqlalchemy import func

    from shared.models import JobRun

    agents = await session.scalar(select(func.count()).select_from(Agent)) or 0
    environments = await session.scalar(
        select(func.count()).select_from(Environment).where(Environment.enabled.is_(True))
    ) or 0
    scans = await session.scalar(select(func.count()).select_from(Scan)) or 0
    findings = await session.scalar(select(func.count()).select_from(Finding)) or 0

    earliest_scan = await session.scalar(select(func.min(Scan.started_at)))
    latest_scan = await session.scalar(select(func.max(Scan.finished_at)))

    last = await session.scalar(select(JobRun).order_by(JobRun.started_at.desc()).limit(1))

    def _iso(value) -> str | None:
        return value.isoformat() if value else None

    return {
        "agents": int(agents),
        "environments": int(environments),
        "scans": int(scans),
        "findings": int(findings),
        "earliest_scan": _iso(earliest_scan),
        "latest_scan": _iso(latest_scan),
        "last_run": (
            {
                "status": last.status,
                "started_at": _iso(last.started_at),
                "finished_at": _iso(last.finished_at),
            }
            if last
            else None
        ),
    }

# --------------------------------------------------------------------------- #
# Executive briefing
#
# Deliberately deterministic: pure SQL for this period against the one before
# it, and prose assembled client-side from fixed thresholds. This app has Azure
# OpenAI configured for the instruction judge and it is still not used here — a
# briefing is the artefact most likely to be read aloud to a customer, and it
# must never be able to invent a number.
#
# This is the first time-bucketed query in the app. Everything else produces a
# trend by ordering rows; a briefing needs to compare two spans, so it groups.
# Both spans are bounded by the most recent scan rather than by today, because
# a report that says "down 40%" when the truth is "nobody has scanned for a
# fortnight" is worse than no report.
# --------------------------------------------------------------------------- #
_GRADES = ("A", "B", "C", "D", "F")
_SEVERITIES = ("blocker", "major", "minor", "info")


async def _scan_ids_in(
    session: AsyncSession, lo: datetime, hi: datetime
) -> list[int]:
    """The latest complete scan per environment within ``[lo, hi)``.

    One scan per environment, not every scan in the window: counting all of
    them would multiply each agent by however many times it happened to be
    scanned, which differs per environment and per period.
    """
    rows = (
        await session.execute(
            select(Scan)
            .where(
                Scan.status == "complete",
                Scan.environment_id.isnot(None),
                Scan.started_at >= lo,
                Scan.started_at < hi,
            )
            .order_by(Scan.started_at.desc())
        )
    ).scalars().all()
    latest: dict[int | None, int] = {}
    for s in rows:
        if s.environment_id not in latest:
            latest[s.environment_id] = s.id
    return list(latest.values())


async def _period_stats(session: AsyncSession, scan_ids: list[int]) -> dict:
    """Agents, average score, grade mix and open findings for a set of scans."""
    empty = {
        "agents": 0,
        "avg_score": None,
        "environments": len(scan_ids),
        "grades": {g: 0 for g in _GRADES},
        "open_findings": 0,
        "findings_by_severity": {s: 0 for s in _SEVERITIES},
    }
    if not scan_ids:
        return empty

    agents = int(
        await session.scalar(
            select(func.count())
            .select_from(AgentScore)
            .where(AgentScore.scan_id.in_(scan_ids))
        )
        or 0
    )
    avg = await session.scalar(
        select(func.avg(AgentScore.score)).where(
            AgentScore.scan_id.in_(scan_ids), AgentScore.score.isnot(None)
        )
    )

    grades = {g: 0 for g in _GRADES}
    for grade, count in (
        await session.execute(
            select(AgentScore.grade, func.count())
            .where(AgentScore.scan_id.in_(scan_ids), AgentScore.grade.isnot(None))
            .group_by(AgentScore.grade)
        )
    ).all():
        if grade in grades:
            grades[grade] = int(count)

    by_severity = {s: 0 for s in _SEVERITIES}
    for severity, count in (
        await session.execute(
            select(Finding.severity, func.count())
            .where(Finding.scan_id.in_(scan_ids), Finding.status == "fail")
            .group_by(Finding.severity)
        )
    ).all():
        if severity in by_severity:
            by_severity[severity] = int(count)

    return {
        "agents": agents,
        "avg_score": round(float(avg)) if avg is not None else None,
        "environments": len(scan_ids),
        "grades": grades,
        "open_findings": sum(by_severity.values()),
        "findings_by_severity": by_severity,
    }


@router.get("/briefing")
async def briefing(
    window_days: int = 30, session: AsyncSession = Depends(get_session)
) -> dict:
    """Executive snapshot: this period against the one before it.

    Every number here comes from SQL. The page turns them into sentences using
    fixed thresholds; nothing is generated.
    """
    period_end = await session.scalar(
        select(func.max(Scan.started_at)).where(Scan.status == "complete")
    )
    if period_end is None:
        return {
            "window_days": window_days,
            "period_end": None,
            "has_data": False,
            "current": await _period_stats(session, []),
            "previous": await _period_stats(session, []),
            "trend": [],
            "worst_agents": [],
            "top_rules": [],
        }

    window = timedelta(days=window_days)
    cur_lo = period_end - window
    # The end bound is exclusive, so nudge past the newest scan to include it.
    cur_hi = period_end + timedelta(seconds=1)
    cur_ids = await _scan_ids_in(session, cur_lo, cur_hi)
    prev_ids = await _scan_ids_in(session, cur_lo - window, cur_lo)

    # Average score per day across the whole history. func.date() is the one
    # bucket expression Postgres and SQLite agree on.
    day = func.date(AgentScore.captured_at)
    trend = [
        {"date": str(d), "avg_score": round(float(avg)) if avg is not None else None}
        for d, avg in (
            await session.execute(
                select(day, func.avg(AgentScore.score))
                .where(AgentScore.score.isnot(None))
                .group_by(day)
                .order_by(day)
            )
        ).all()
    ]

    # The agents worth naming: lowest scoring in the current period.
    worst = [
        {
            "bot_id": r.bot_id,
            "agent_name": r.agent_name,
            "score": r.score,
            "grade": r.grade,
            "scan_id": r.scan_id,
        }
        for r in (
            await session.execute(
                select(AgentScore)
                .where(AgentScore.scan_id.in_(cur_ids), AgentScore.score.isnot(None))
                .order_by(AgentScore.score.asc())
                .limit(5)
            )
        ).scalars().all()
    ] if cur_ids else []

    # The rules failing most often — what to fix once to fix it everywhere.
    top_rules = [
        {"rule_id": rule_id, "name": name, "severity": severity, "agents": int(count)}
        for rule_id, name, severity, count in (
            (
                await session.execute(
                    select(
                        Finding.rule_id, Finding.name, Finding.severity, func.count()
                    )
                    .where(Finding.scan_id.in_(cur_ids), Finding.status == "fail")
                    .group_by(Finding.rule_id, Finding.name, Finding.severity)
                    .order_by(func.count().desc())
                    .limit(5)
                )
            ).all()
            if cur_ids
            else []
        )
    ]

    current = await _period_stats(session, cur_ids)
    return {
        "window_days": window_days,
        "period_end": period_end.isoformat(),
        "has_data": bool(cur_ids) and current["agents"] > 0,
        "current": current,
        "previous": await _period_stats(session, prev_ids),
        "trend": trend,
        "worst_agents": worst,
        "top_rules": top_rules,
    }


# --------------------------------------------------------------------------- #
# Agent creators
#
# Named honestly. The ask was for a tenant-users listing like the sibling
# solutions have, and this app cannot build one: it has no directory data at
# all — no user table, no Entra sync — because the worker reads Dataverse, not
# Graph. The only trace of a person anywhere in this schema is the maker
# Copilot Studio stamps on an agent.
#
# So this lists people who have *made* an agent, and says so. Calling it
# "Tenant users" would have been a listing that silently omits everyone who has
# never built an agent, which in most tenants is nearly everybody — a listing
# that is wrong in a way the reader cannot see is worse than one with a
# narrower name.
# --------------------------------------------------------------------------- #
@router.get("/agent-creators")
async def agent_creators(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Every person recorded as creating an agent, with how their agents score.

    Scores come from each agent's most recent scored appearance, so a creator's
    average reflects the current state of their agents rather than whichever
    scan happened to run last in their environment.

    Deliberately four queries regardless of how many agents there are. The
    personal view can afford a per-agent lookup because it only ever walks one
    person's agents; this page walks every agent in the tenant, so the same
    pattern would have been two queries per agent across potentially hundreds.
    """
    env_names = {
        e.id: e.display_name
        for e in (await session.execute(select(Environment))).scalars().all()
    }

    agents = (
        await session.execute(
            select(Agent).where(Agent.created_by_upn.isnot(None))
        )
    ).scalars().all()

    # Latest scored appearance per agent, in one query: group to find each
    # bot's newest capture, then join back for the whole row.
    newest = (
        select(
            AgentScore.bot_id.label("bot_id"),
            func.max(AgentScore.captured_at).label("ts"),
        )
        .where(AgentScore.bot_id.isnot(None))
        .group_by(AgentScore.bot_id)
        .subquery()
    )
    latest_by_bot: dict[str, AgentScore] = {}
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
        # Two scans can share a timestamp; first one wins, as the ordered
        # per-agent query it replaces also did.
        latest_by_bot.setdefault(row.bot_id, row)

    # Open findings for every (scan, agent) pair, also in one query.
    open_by_key: dict[tuple[int, str], int] = {
        (scan_id, agent_name): int(count)
        for scan_id, agent_name, count in (
            await session.execute(
                select(Finding.scan_id, Finding.agent_name, func.count())
                .where(Finding.status == "fail", Finding.agent_name.isnot(None))
                .group_by(Finding.scan_id, Finding.agent_name)
            )
        ).all()
    }

    # Group case-insensitively: Dataverse and Entra disagree about casing, and
    # one person must not appear as two rows because of it.
    creators: dict[str, dict] = {}
    for agent in agents:
        key = (agent.created_by_upn or "").lower()
        if not key:
            continue
        row = creators.setdefault(
            key,
            {
                "upn": agent.created_by_upn,
                "display_name": agent.created_by_name,
                "agents": 0,
                "scores": [],
                "grades": {g: 0 for g in _GRADES},
                "open_findings": 0,
                "environment_ids": set(),
            },
        )
        # Prefer a real name over None if any of their agents carries one.
        row["display_name"] = row["display_name"] or agent.created_by_name
        row["agents"] += 1

        score_row = latest_by_bot.get(agent.bot_id) if agent.bot_id else None
        env_id = (
            score_row.environment_id if score_row is not None else agent.environment_id
        )
        if env_id is not None:
            row["environment_ids"].add(env_id)
        if score_row is not None:
            if score_row.score is not None:
                row["scores"].append(score_row.score)
            if score_row.grade in row["grades"]:
                row["grades"][score_row.grade] += 1
            row["open_findings"] += open_by_key.get(
                (score_row.scan_id, score_row.agent_name), 0
            )

    out = []
    for row in creators.values():
        scores = row["scores"]
        out.append(
            {
                "upn": row["upn"],
                "display_name": row["display_name"],
                "agents": row["agents"],
                "scored_agents": len(scores),
                "avg_score": round(sum(scores) / len(scores)) if scores else None,
                "grades": row["grades"],
                "open_findings": row["open_findings"],
                "environments": sorted(
                    env_names[e] for e in row["environment_ids"] if e in env_names
                ),
            }
        )
    # Worst average first: this page is opened to answer "who is making agents
    # that need attention", and the default sort should answer it on arrival
    # rather than after a click. Creators with nothing scored sort last — they
    # are an unknown, not a problem.
    out.sort(key=lambda r: (r["avg_score"] is None, r["avg_score"] or 0))
    return out


# --------------------------------------------------------------------------- #
# Personal view — "agents you created"
#
# This platform has no user dimension: the only trace of a person is the UPN
# stamped on an agent by Copilot Studio. So "mine" means
# ``agents.created_by_upn`` equal to the UPN in the caller's token, compared
# case-insensitively because Dataverse and Entra disagree about casing in
# practice.
#
# Every route below derives the person from the token. There is deliberately no
# "which user?" parameter: if a caller could name the user, any viewer could
# read someone else's agents by editing a URL.
# --------------------------------------------------------------------------- #
async def _me_upn(user: CurrentUser, session: AsyncSession) -> str:
    """The signed-in person's UPN, or 404.

    Goes through :func:`personal_view_upn` rather than reading the claim
    directly, so the local admin standing in for a demo persona reaches these
    routes too — otherwise the pages would render and every call behind them
    would 404.
    """
    upn = await personal_view_upn(user, session)
    if not upn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "There is no personal view for this account. Sign in with your "
                "work account to see the agents you created."
            ),
        )
    return upn


async def _my_agent_rows(session: AsyncSession, upn: str) -> list[Agent]:
    """Agent metadata rows created by this person.

    NULL ``created_by_upn`` never matches (``lower(NULL)`` is NULL), so an agent
    with unknown provenance is nobody's rather than everybody's.
    """
    return list(
        (
            await session.execute(
                select(Agent)
                .where(func.lower(Agent.created_by_upn) == upn.lower())
                .order_by(Agent.display_name)
            )
        )
        .scalars()
        .all()
    )


async def _latest_score(session: AsyncSession, bot_id: str) -> AgentScore | None:
    """Most recent scored appearance of one agent, across all scans."""
    return await session.scalar(
        select(AgentScore)
        .where(AgentScore.bot_id == bot_id)
        .order_by(AgentScore.captured_at.desc(), AgentScore.id.desc())
        .limit(1)
    )


async def _open_findings(session: AsyncSession, scan_id: int, agent_name: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Finding)
            .where(
                Finding.scan_id == scan_id,
                Finding.agent_name == agent_name,
                Finding.status == "fail",
            )
        )
        or 0
    )


async def _my_agent_cards(session: AsyncSession, upn: str) -> list[dict]:
    env_rows = {
        e.id: e for e in (await session.execute(select(Environment))).scalars().all()
    }
    out: list[dict] = []
    for agent in await _my_agent_rows(session, upn):
        score_row = await _latest_score(session, agent.bot_id) if agent.bot_id else None
        env_id = (
            score_row.environment_id if score_row is not None else agent.environment_id
        )
        env = env_rows.get(env_id) if env_id is not None else None
        out.append(
            {
                "bot_id": agent.bot_id,
                "agent_name": (
                    score_row.agent_name if score_row is not None else agent.display_name
                ),
                "solution_name": score_row.solution_name if score_row else None,
                "publish_state": (
                    score_row.publish_state if score_row else agent.publish_state
                ),
                "score": score_row.score if score_row else None,
                "grade": score_row.grade if score_row else None,
                "scan_id": score_row.scan_id if score_row else None,
                "environment_id": env_id,
                "environment_name": env.display_name if env else None,
                "open_findings": (
                    await _open_findings(session, score_row.scan_id, score_row.agent_name)
                    if score_row is not None
                    else 0
                ),
                "modified_on": (
                    agent.modified_on.isoformat() if agent.modified_on else None
                ),
            }
        )
    return out


@me_router.get("/summary")
async def my_summary(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Rollup over the agents this person created."""
    cards = await _my_agent_cards(session, await _me_upn(user, session))
    scored = [c["score"] for c in cards if c["score"] is not None]
    grades = [c["grade"] for c in cards if c["grade"]]
    worst = max(grades) if grades else None
    return {
        "agents": len(cards),
        "scored_agents": len(scored),
        "avg_score": round(sum(scored) / len(scored)) if scored else None,
        # Worst grade is the useful one to surface: it is what needs attention.
        "worst_grade": worst,
        # How many agents sit on that worst grade. One D is a bad afternoon;
        # six is a pattern, and the tile should be able to say which.
        "worst_grade_agents": sum(1 for g in grades if g == worst) if worst else 0,
        "open_findings": sum(c["open_findings"] for c in cards),
        # How many agents carry at least one open finding. The total alone
        # cannot distinguish one badly broken agent from twelve slightly
        # untidy ones.
        "agents_with_findings": sum(1 for c in cards if c["open_findings"] > 0),
        "environments": len({c["environment_id"] for c in cards}),
        "has_data": bool(cards),
    }


@me_router.get("/agents")
async def my_agents(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Every agent this person created, with its latest score and open findings."""
    return await _my_agent_cards(session, await _me_upn(user, session))


@me_router.get("/agents/{bot_id}")
async def my_agent_detail(
    bot_id: str,
    user: CurrentUser = Depends(get_current_user),
    scan_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Full scorecard for one of this person's own agents.

    ``bot_id`` names an agent rather than a user, but it is still somebody's
    agent, so ownership is confirmed against the token first — otherwise
    guessing ids would read other people's scorecards. A non-owner gets 404
    rather than 403 so the endpoint does not confirm that the id exists.
    """
    upn = await _me_upn(user, session)
    agent = await session.scalar(
        select(Agent).where(
            Agent.bot_id == bot_id,
            func.lower(Agent.created_by_upn) == upn.lower(),
        )
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    if scan_id is None:
        score_row = await _latest_score(session, bot_id)
        if score_row is None:
            raise HTTPException(status_code=404, detail="Agent has not been scored yet")
        scan_id = score_row.scan_id
    return await agent_detail(bot_id=bot_id, scan_id=scan_id, session=session)


@me_router.get("/agents/{bot_id}/history")
async def my_agent_history(
    bot_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Score history for one of this person's own agents."""
    upn = await _me_upn(user, session)
    owned = await session.scalar(
        select(Agent.id).where(
            Agent.bot_id == bot_id,
            func.lower(Agent.created_by_upn) == upn.lower(),
        )
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await agent_history(bot_id=bot_id, session=session)
