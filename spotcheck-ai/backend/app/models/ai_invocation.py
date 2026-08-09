"""ai_invocations テーブル（docs/02-database.md 2.7）。AI呼び出しの監査ログ。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AiInvocation(Base):
    __tablename__ = "ai_invocations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    #: task_review / image_validation / environment_check / result_summary
    purpose: Mapped[str] = mapped_column(String, nullable=False)
    #: task / submission
    related_type: Mapped[str | None] = mapped_column(String)
    related_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: 実際に使われたモデル名（OrcaRouterの応答から取得）
    model: Mapped[str | None] = mapped_column(String)
    #: 画像はURL参照に置換して保存する（base64は保存しない）
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    is_stub: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
