"""payments テーブル（docs/02-database.md 2.6 / D-03）。

実決済は行わない。取引の記録のみを残す。
**外部決済SDKの導入・カード番号や口座番号の保存は行わない。**
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import PaymentDirection, PaymentStatus


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    #: 支払いの根拠となった提出
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id")
    )
    #: 課金先または支払先
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    direction: Mapped[PaymentDirection] = mapped_column(
        Enum(
            PaymentDirection,
            name="payment_direction",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=text("'stub_pending'"),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
