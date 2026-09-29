"""Add app_config.demo_persona_upn.

Loading demo data binds the local admin account to one of the seeded agent
creators, and this is where that binding lives. Without it the personal pages
cannot be reached at all without an Entra sign-in — ``has_personal_view`` needs
a directory identity and the password admin has none — so anyone evaluating the
product with demo data never sees the pages the README advertises.

This app has no directory of its own: the only trace of a person in the schema
is the UPN Copilot Studio stamps on an agent it created. So the binding holds a
``created_by_upn``, which is what the personal view already matches on, rather
than the Entra object ID its sibling solutions use.

It sits on ``app_config`` beside the rest of the configuration rather than in a
table of operational state, so it is discoverable from the model by anyone
asking "what is this deployment set up to do".

NULL on upgrade, and set only by an explicit demo seed. It is cleared when demo
data is cleared, and retired automatically after the first successful real scan,
so a tenant that seeds, looks, then connects a real environment is left exactly
where it started.

Revision ID: 0009_demo_persona
Revises: 0008_admin_group
Create Date: 2026-09-29
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009_demo_persona"
down_revision: str | None = "0008_admin_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_config", sa.Column("demo_persona_upn", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("app_config", "demo_persona_upn")
