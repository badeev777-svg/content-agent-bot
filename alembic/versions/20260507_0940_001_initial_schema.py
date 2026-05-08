"""initial schema: users, user_profiles, content_plans, posts

Revision ID: 001
Revises:
Create Date: 2026-05-07

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SUBSCRIPTION = sa.Enum("free", "paid", name="subscription", native_enum=False, length=16)
TONE = sa.Enum("expert", "friendly", "provocative", name="tone", native_enum=False, length=16)
PLATFORM = sa.Enum(
    "telegram", "vk", "stories", "vc_ru", name="platform", native_enum=False, length=16
)
POST_TYPE = sa.Enum(
    "engagement", "expertise", "trust", "sale", name="post_type", native_enum=False, length=16
)
FEEDBACK = sa.Enum(
    "none", "liked", "rewritten", name="feedback", native_enum=False, length=16
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("subscription", SUBSCRIPTION, nullable=False, server_default="free"),
        sa.Column("gens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sub_expires", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "user_profiles",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("niche", sa.Text(), nullable=True),
        sa.Column("tone", TONE, nullable=True),
        sa.Column("forbidden", sa.JSON(), nullable=True),
        sa.Column("formats", sa.JSON(), nullable=True),
        sa.Column("example_posts", sa.JSON(), nullable=True),
        sa.Column("style_notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "content_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_summary", sa.Text(), nullable=True),
        sa.Column("platforms", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_content_plans_user_id", "content_plans", ["user_id"])

    op.create_table(
        "posts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "plan_id",
            sa.String(length=36),
            sa.ForeignKey("content_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("platform", PLATFORM, nullable=False),
        sa.Column("post_type", POST_TYPE, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("hashtags", sa.JSON(), nullable=True),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column("rec_time", sa.String(length=16), nullable=True),
        sa.Column("feedback", FEEDBACK, nullable=False, server_default="none"),
        sa.Column("rewrites_used", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_posts_plan_id", "posts", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_posts_plan_id", table_name="posts")
    op.drop_table("posts")
    op.drop_index("ix_content_plans_user_id", table_name="content_plans")
    op.drop_table("content_plans")
    op.drop_table("user_profiles")
    op.drop_table("users")
