"""submissions テーブル（docs/02-database.md 2.5）。ワーカーの提出物。"""

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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import ValidationStatus


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "attempt_no", name="uq_submission_attempt"),
        CheckConstraint("attempt_no BETWEEN 1 AND 3", name="ck_attempt_no"),
        Index("idx_submissions_task", "task_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_assignments.id"), nullable=False
    )
    #: 検索用の非正規化
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    #: **原本。クライアントには絶対に返さない**
    raw_image_url: Mapped[str] = mapped_column(String, nullable=False)
    #: マスキング済み画像（Phase 5 で設定される）
    processed_image_url: Mapped[str | None] = mapped_column(String)
    captured_lat: Mapped[float] = mapped_column(Float, nullable=False)
    captured_lng: Mapped[float] = mapped_column(Float, nullable=False)
    captured_accuracy_m: Mapped[float | None] = mapped_column(Float)
    #: 端末側の撮影時刻（D-02）
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: サーバー受信時刻
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    device_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    exif_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ai_validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(
            ValidationStatus,
            name="validation_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=text("'pending'"),
    )
    ai_score: Mapped[int | None] = mapped_column(Integer)
    ai_feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    location_check: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    masking_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reality_score: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
