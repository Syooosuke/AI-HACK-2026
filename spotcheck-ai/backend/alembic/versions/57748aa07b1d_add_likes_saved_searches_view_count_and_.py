"""いいね・保存した検索条件・閲覧数・サムネイルを追加する

投稿一覧（ハート欄）と、SOLD / NEW / HOT タグの表示に必要な情報を持たせる。

Revision ID: 57748aa07b1d
Revises: 8f2a41c7d9b3
Create Date: 2026-08-11 15:03:51.983810

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "57748aa07b1d"
down_revision: str | None = "8f2a41c7d9b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lng", sa.Float(), nullable=False),
        sa.Column("location_address", sa.String(), nullable=True),
        sa.Column("radius_km", sa.Float(), server_default=sa.text("5"), nullable=False),
        sa.Column("sort", sa.String(), server_default=sa.text("'distance'"), nullable=False),
        sa.Column("last_match_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_saved_searches_user",
        "saved_searches",
        ["user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "task_likes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "task_id", name="uq_task_like_user_task"),
    )
    op.create_index(
        "idx_task_likes_user",
        "task_likes",
        ["user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.add_column("tasks", sa.Column("thumbnail_image_url", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("thumbnail_source", sa.String(), nullable=True))
    op.add_column(
        "tasks", sa.Column("view_count", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    op.add_column(
        "tasks", sa.Column("like_count", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )


def downgrade() -> None:
    op.drop_column("tasks", "like_count")
    op.drop_column("tasks", "view_count")
    op.drop_column("tasks", "thumbnail_source")
    op.drop_column("tasks", "thumbnail_image_url")
    op.drop_index("idx_task_likes_user", table_name="task_likes")
    op.drop_table("task_likes")
    op.drop_index("idx_saved_searches_user", table_name="saved_searches")
    op.drop_table("saved_searches")
