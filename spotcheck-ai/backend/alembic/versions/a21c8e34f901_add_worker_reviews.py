"""add worker reviews

Revision ID: a21c8e34f901
Revises: 57748aa07b1d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a21c8e34f901"
down_revision: str | None = "57748aa07b1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_worker_reviews_rating"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", name="uq_worker_reviews_submission"),
    )
    op.create_index("ix_worker_reviews_submission_id", "worker_reviews", ["submission_id"])
    op.create_index("ix_worker_reviews_task_id", "worker_reviews", ["task_id"])
    op.create_index("ix_worker_reviews_reviewer_id", "worker_reviews", ["reviewer_id"])
    op.create_index("ix_worker_reviews_worker_id", "worker_reviews", ["worker_id"])


def downgrade() -> None:
    op.drop_table("worker_reviews")
