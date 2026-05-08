"""add daily rewrite limits to users

Revision ID: 003
Revises: 002
Create Date: 2026-05-07

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("rewrites_used_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("rewrites_reset_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "rewrites_reset_at")
    op.drop_column("users", "rewrites_used_today")
