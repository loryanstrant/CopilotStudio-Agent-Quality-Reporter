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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import CurrentUser, get_current_user, require_org_view
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
def _me_upn(user: CurrentUser) -> str:
    """The signed-in person's UPN, or 404."""
    if not user.upn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "There is no personal view for this account. Sign in with your "
                "work account to see the agents you created."
            ),
        )
    return user.upn


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
    cards = await _my_agent_cards(session, _me_upn(user))
    scored = [c["score"] for c in cards if c["score"] is not None]
    grades = [c["grade"] for c in cards if c["grade"]]
    return {
        "agents": len(cards),
        "scored_agents": len(scored),
        "avg_score": round(sum(scored) / len(scored)) if scored else None,
        # Worst grade is the useful one to surface: it is what needs attention.
        "worst_grade": max(grades) if grades else None,
        "open_findings": sum(c["open_findings"] for c in cards),
        "environments": len({c["environment_id"] for c in cards}),
        "has_data": bool(cards),
    }


@me_router.get("/agents")
async def my_agents(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Every agent this person created, with its latest score and open findings."""
    return await _my_agent_cards(session, _me_upn(user))


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
    upn = _me_upn(user)
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
    upn = _me_upn(user)
    owned = await session.scalar(
        select(Agent.id).where(
            Agent.bot_id == bot_id,
            func.lower(Agent.created_by_upn) == upn.lower(),
        )
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await agent_history(bot_id=bot_id, session=session)
