"""users テーブル（docs/02-database.md 2.1）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import UserRole

#: 検品合格時の trust_score 加点（docs/02-database.md 2.1）
TRUST_SCORE_ON_APPROVED = Decimal("2.0")
#: 再撮影上限超過による失格時の減点
TRUST_SCORE_ON_FAILED = Decimal("-5.0")
TRUST_SCORE_MIN = Decimal(0)
TRUST_SCORE_MAX = Decimal(100)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, unique=True)
    trust_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), nullable=False, server_default=text("50.0")
    )
    completed_task_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    avatar_url: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def apply_trust_score_delta(self, delta: Decimal) -> None:
        """trust_score を 0〜100 にクリップして更新する。"""
        self.trust_score = min(TRUST_SCORE_MAX, max(TRUST_SCORE_MIN, self.trust_score + delta))
