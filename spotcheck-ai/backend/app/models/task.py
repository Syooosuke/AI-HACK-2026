"""tasks / task_reference_images テーブル（docs/02-database.md 2.2, 2.3）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import TaskStatus

#: 1依頼あたりの参考画像の上限（docs/02-database.md 2.3）
MAX_REFERENCE_IMAGES = 3


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("reward_amount > 0", name="ck_tasks_reward_amount"),
        CheckConstraint(
            "required_worker_count BETWEEN 1 AND 10", name="ck_tasks_required_worker_count"
        ),
        CheckConstraint(
            "min_worker_rating IS NULL OR (min_worker_rating >= 1.0 AND min_worker_rating <= 5.0)",
            name="ck_tasks_min_worker_rating",
        ),
        Index("idx_tasks_status_deadline", "status", "deadline_at"),
        Index("idx_tasks_location", "location_lat", "location_lng"),
        Index("idx_tasks_client", "client_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location_lat: Mapped[float] = mapped_column(Float, nullable=False)
    location_lng: Mapped[float] = mapped_column(Float, nullable=False)
    location_address: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reward_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    required_worker_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    approved_worker_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    #: 受注できるワーカーの最低平均評価（1.0〜5.0）。None なら誰でも受注できる。
    #: 評価がまだ無いワーカーは足切りしない（新規が永久に受注できなくなるため）。
    min_worker_rating: Mapped[float | None] = mapped_column(Float)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=text("'screening'"),
    )
    review_score: Mapped[int | None] = mapped_column(Integer)
    review_summary: Mapped[str | None] = mapped_column(Text)
    review_feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result_summary: Mapped[str | None] = mapped_column(Text)
    #: 投稿一覧に出す正方形サムネイルの保存キー（配信用バケット）。未生成なら None
    thumbnail_image_url: Mapped[str | None] = mapped_column(String)
    #: サムネイルの由来: reference（参考画像）/ generated（AI生成）/ streetview / placeholder
    thumbnail_source: Mapped[str | None] = mapped_column(String)
    #: 詳細を開かれた回数。HOTタグの判定に使う
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    #: いいねの数。task_likes の集計値をここに持ち、一覧のN+1を避ける
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    reference_images: Mapped[list[TaskReferenceImage]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskReferenceImage.sort_order",
        lazy="selectin",
    )


class TaskReferenceImage(Base):
    """クライアントが「期待する画像イメージ」としてアップロードする参考画像。"""

    __tablename__ = "task_reference_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    image_url: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    task: Mapped[Task] = relationship(back_populates="reference_images")
