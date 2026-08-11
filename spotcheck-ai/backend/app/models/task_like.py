"""task_likes テーブル。依頼（投稿）への「いいね」。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TaskLike(Base):
    """1ユーザー×1依頼につき1行。取り消したら行を消す（履歴は残さない）。"""

    __tablename__ = "task_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "task_id", name="uq_task_like_user_task"),
        # ハート欄の一覧は「自分のいいねを新しい順」で引くため
        Index("idx_task_likes_user", "user_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
