"""Add agent_creators — directory details for the people who build agents.

This app has never had any directory data: its worker reads Dataverse and
Application Insights, so the only trace of a person in the schema was the UPN
Copilot Studio stamps on an agent. That made two things impossible — showing a
real name instead of a sign-in address, and comparing somebody with their team.

What this table is **not** is a tenant directory. Rows are written only for
UPNs already present on an agent, by a Graph lookup of exactly those people; a
tenant-wide sync was explicitly ruled out. See
``docs/specs/comparisons-and-timelines.md`` and ``worker/creators.py``.

``resolved`` carries whether Graph answered. A creator it cannot resolve keeps
a row with ``resolved=False`` so their agents never vanish from a listing that
joins through here.

Keyed on the lower-cased UPN rather than the Entra object id, because an
unresolved creator has no object id and would therefore have no primary key.

Revision ID: 0010_agent_creators
Revises: 0009_demo_persona
Create Date: 2026-09-30
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_agent_creators"
down_revision: str | None = "0009_demo_persona"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_creators",
        sa.Column("upn", sa.Text(), primary_key=True),
        sa.Column("entra_user_id", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("job_title", sa.Text(), nullable=True),
        sa.Column("office_location", sa.Text(), nullable=True),
        sa.Column("manager_id", sa.Text(), nullable=True),
        sa.Column("manager_name", sa.Text(), nullable=True),
        sa.Column(
            "resolved", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Department and manager are the two groupings the team comparison uses, and
    # it resolves a team on every load of a personal page.
    op.create_index("ix_agent_creators_department", "agent_creators", ["department"])
    op.create_index("ix_agent_creators_manager_id", "agent_creators", ["manager_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_creators_manager_id", table_name="agent_creators")
    op.drop_index("ix_agent_creators_department", table_name="agent_creators")
    op.drop_table("agent_creators")
