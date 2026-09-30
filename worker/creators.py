"""Resolve the people who created agents against the directory.

The unit of work is: read the distinct ``created_by_upn`` values already sitting
on ``agents``, ask Graph about **those** UPNs, and store what comes back. It is
a join between data the app already holds and the directory — not an import of
the directory, which was ruled out. :mod:`worker.graph` enforces that by having
no way to list users at all.

Three behaviours worth knowing before reading the code:

* **An unresolvable creator is kept.** Somebody who has left, or a service
  principal that built an agent, gets a row with ``resolved=False`` and is shown
  by UPN. Dropping them would remove their agents from the creators listing, and
  a listing that is missing rows for a reason the reader cannot see is worse
  than one with an ugly-looking name in it.
* **Missing consent stops the run, not the scan.** Without ``User.Read.All``
  every lookup would return the same 403, so the first one ends the sync and the
  reason is recorded on the job run for Settings and Scan history to show. A
  scan that scored every agent correctly is not a failed scan because the
  directory is unavailable.
* **Freshness, not idempotence, decides who is looked up.** Anything resolved
  within :data:`FRESH_FOR` is skipped, so a nightly scan of a stable tenant
  makes no Graph calls at all.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.crypto import decrypt
from shared.models import Agent, AgentCreator, AppConfig, JobRun
from worker.graph import (
    GraphConsentError,
    GraphError,
    GraphNotFound,
    GraphUserLookup,
)

logger = logging.getLogger("worker.creators")

# The job_runs kind for this sync. Deliberately not "users", which is the
# sibling solutions' word for a whole-tenant directory import — the exact thing
# this app does not do. A run log that borrows that word describes this app as
# doing something it refuses to do.
JOB_NAME = "creators"

# A directory record is re-read only when it is older than this. Departments and
# managers change on the scale of months; agents are scanned nightly.
FRESH_FOR = timedelta(days=7)


class CreatorSyncSkipped(RuntimeError):
    """The sync could not start (no credentials, nothing to look up)."""


async def pending_upns(
    session: AsyncSession, *, now: datetime | None = None, force: bool = False
) -> list[str]:
    """Creator UPNs needing a lookup: on an agent, and not freshly resolved.

    Lower-cased, because ``agents.created_by_upn`` comes from Dataverse with
    whatever casing the maker typed and two casings of one person would compare
    as two colleagues.
    """
    now = now or datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(func.distinct(func.lower(Agent.created_by_upn))).where(
                Agent.created_by_upn.isnot(None), Agent.created_by_upn != ""
            )
        )
    ).scalars().all()
    upns = sorted({str(u) for u in rows if u})
    if force:
        return upns

    known = {
        c.upn: c
        for c in (await session.execute(select(AgentCreator))).scalars().all()
    }
    pending: list[str] = []
    for upn in upns:
        row = known.get(upn)
        if row is None:
            pending.append(upn)
            continue
        updated = row.updated_at
        if updated is not None and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        # An unresolved row is retried on the next sync rather than being cached
        # for a week: the usual cause is a lookup that failed once.
        if not row.resolved or updated is None or now - updated > FRESH_FOR:
            pending.append(upn)
    return pending


async def sync_creators(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    force: bool = False,
    lookup_factory=None,
) -> dict:
    """Look up the agent creators that need it, and record the run.

    ``lookup_factory`` exists for the tests: a zero-argument callable returning
    something shaped like :class:`~worker.graph.GraphUserLookup`. Production
    passes nothing and the real client is built from the stored credentials.

    Returns a stats dict. Raises :class:`CreatorSyncSkipped` when there is
    nothing it could do — no credentials, or no creators — so a caller can tell
    "did not run" apart from "ran and resolved nobody".
    """
    async with session_factory() as session:
        cfg = await session.get(AppConfig, 1)
        have_credentials = bool(
            cfg and cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted
        )
        if not have_credentials and lookup_factory is None:
            raise CreatorSyncSkipped(
                "Directory lookups need the Dataverse service principal to be "
                "configured, with the User.Read.All Graph permission."
            )

        upns = await pending_upns(session, force=force)
        if not upns:
            raise CreatorSyncSkipped("Every agent creator is already up to date.")

        run = JobRun(job_name=JOB_NAME, status="running")
        session.add(run)
        await session.commit()

        resolved = 0
        unresolved = 0
        failed = 0
        consent_error: str | None = None

        def build_lookup():
            if lookup_factory is not None:
                return lookup_factory()
            assert cfg is not None  # guarded by have_credentials above
            return GraphUserLookup(
                tenant_id=str(cfg.tenant_id),
                client_id=str(cfg.client_id),
                client_secret=str(decrypt(cfg.client_secret_encrypted)),
            )

        try:
            async with build_lookup() as graph:
                # Sequential at this level; the client's own semaphore bounds
                # concurrency. Creator counts are in the tens, not thousands,
                # and a readable failure matters more here than wall-clock.
                for upn in upns:
                    try:
                        details = await graph.get_user(upn)
                    except GraphConsentError as exc:
                        consent_error = str(exc)
                        logger.warning("Creator sync stopped: %s", exc)
                        break
                    except GraphNotFound:
                        await _store_unresolved(
                            session, upn, "No directory record for this sign-in address."
                        )
                        unresolved += 1
                        continue
                    except GraphError as exc:
                        await _store_unresolved(session, upn, str(exc)[:300])
                        failed += 1
                        continue
                    await _store_resolved(session, upn, details)
                    resolved += 1
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.stats = {"error": str(exc)[:500], "creators": len(upns)}
            await session.commit()
            logger.exception("Creator directory sync failed")
            raise

        stats: dict = {
            "creators": resolved + unresolved + failed,
            "resolved": resolved,
            "unresolved": unresolved,
            "lookup_errors": failed,
        }
        if consent_error:
            # Recorded as a failed run: the administrator has something to do.
            # The scan that triggered this is unaffected.
            stats["error"] = consent_error
            run.status = "failed"
        else:
            run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.stats = stats
        await session.commit()

        logger.info("Creator directory sync: %s", stats)
        return stats


async def _store_resolved(session: AsyncSession, upn: str, details: dict) -> None:
    row = await session.get(AgentCreator, upn)
    if row is None:
        row = AgentCreator(upn=upn)
        session.add(row)
    row.entra_user_id = details.get("entra_user_id")
    row.display_name = details.get("display_name")
    row.department = (details.get("department") or None)
    row.job_title = details.get("job_title")
    row.office_location = details.get("office_location")
    row.manager_id = details.get("manager_id")
    row.manager_name = details.get("manager_name")
    row.resolved = True
    row.error = None
    row.updated_at = datetime.now(timezone.utc)


async def _store_unresolved(session: AsyncSession, upn: str, error: str) -> None:
    """Keep the creator, without directory details. See the module docstring."""
    row = await session.get(AgentCreator, upn)
    if row is None:
        row = AgentCreator(upn=upn)
        session.add(row)
    row.resolved = False
    row.error = error
    row.updated_at = datetime.now(timezone.utc)


async def sync_creators_quietly(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict | None:
    """Run the sync, swallowing every failure. For use at the end of a scan.

    A scan that scored every agent has succeeded whatever the directory did, so
    this never propagates. The reason is on the job run either way, which is
    what Scan history and Settings read.
    """
    try:
        return await sync_creators(session_factory)
    except CreatorSyncSkipped as exc:
        logger.info("Creator directory sync skipped: %s", exc)
        return None
    except Exception:  # noqa: BLE001
        logger.warning("Creator directory sync failed; scan unaffected", exc_info=True)
        return None
