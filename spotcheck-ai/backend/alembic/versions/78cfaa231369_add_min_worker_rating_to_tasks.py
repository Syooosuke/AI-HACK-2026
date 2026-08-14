"""add min_worker_rating to tasks

依頼者が「平均評価◯以上のワーカーだけ受注できる」条件を付けられるようにする。
NULL は条件なし。既存の依頼はすべて NULL（＝誰でも受注可）のままで、挙動は変わらない。

Revision ID: 78cfaa231369
Revises: 335d3aa1b952
Create Date: 2026-08-14 13:04:41.478826

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "78cfaa231369"
down_revision: str | None = "335d3aa1b952"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("min_worker_rating", sa.Float(), nullable=True))
    # 星の範囲を外れた値が入らないようDB側でも縛る
    op.create_check_constraint(
        "ck_tasks_min_worker_rating",
        "tasks",
        "min_worker_rating IS NULL OR (min_worker_rating >= 1.0 AND min_worker_rating <= 5.0)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tasks_min_worker_rating", "tasks", type_="check")
    op.drop_column("tasks", "min_worker_rating")
