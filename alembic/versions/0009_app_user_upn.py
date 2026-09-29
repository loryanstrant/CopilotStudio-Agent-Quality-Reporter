"""Add app_users.upn.

A local password account has no directory identity, and agents are attributed
by their creator's UPN, so there was no "me" to filter a personal view down to.
Anyone evaluating this product with demo data could therefore never reach the
personal pages the README advertises — sign-in worked, the pages were routed,
and the only way in was a real Entra tenant.

This gives a local account somewhere to record a UPN. Loading demo data sets it
to one of the seeded agent creators; a real deployment can leave it NULL, which
behaves exactly as before.

Revision ID: 0009_app_user_upn
Revises: 0008_admin_group
Create Date: 2026-09-29
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009_app_user_upn"
down_revision: str | None = "0008_admin_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_users", sa.Column("upn", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_users", "upn")
