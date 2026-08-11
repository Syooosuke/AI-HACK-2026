"""saved_searches テーブル。ハート欄に並べる「保存した検索条件」。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

#: 1ユーザーが保存できる検索条件の上限。無制限に増やさないための歯止め。
MAX_SAVED_SEARCHES = 20


class SavedSearch(Base):
    """検索した地点・範囲・並び順を名前付きで保存する。"""

    __tablename__ = "saved_searches"
    __table_args__ = (Index("idx_saved_searches_user", "user_id", text("created_at DESC")),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: 一覧に出す名前。未入力なら住所や座標から自動生成する。
    label: Mapped[str] = mapped_column(String, nullable=False)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False)
    location_address: Mapped[str | None] = mapped_column(String)
    radius_km: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("5"))
    #: distance / reward / deadline
    sort: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'distance'"))
    #: 一覧を開いたときに「この条件で何件あるか」を出すための最終確認件数（任意）
    last_match_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
