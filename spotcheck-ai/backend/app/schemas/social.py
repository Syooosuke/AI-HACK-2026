"""いいね・保存した検索条件（ハート欄）のスキーマ。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.task import NearbyTask


class LikeResponse(CamelModel):
    """いいねの追加・取消の結果。ボタンの表示切替に使う。"""

    task_id: uuid.UUID
    liked: bool
    like_count: int


class LikedTaskListResponse(CamelModel):
    """ハート欄の上半分（いいねした投稿）。いいねした順に新しいものから並ぶ。"""

    tasks: list[NearbyTask]


class SavedSearchCreateRequest(CamelModel):
    """検索結果の画面から「この条件を保存」で送る内容。"""

    label: str | None = Field(default=None, max_length=60)
    center_lat: float = Field(ge=-90, le=90)
    center_lng: float = Field(ge=-180, le=180)
    location_address: str | None = Field(default=None, max_length=200)
    radius_km: float = Field(default=5, ge=0.5, le=50)
    sort: Literal["distance", "reward", "deadline"] = "distance"


class SavedSearchItem(CamelModel):
    id: uuid.UUID
    label: str
    center_lat: float
    center_lng: float
    location_address: str | None = None
    radius_km: float
    sort: str
    #: 保存時点で該当した件数（目安として一覧に出す）
    last_match_count: int | None = None
    created_at: datetime


class SavedSearchListResponse(CamelModel):
    searches: list[SavedSearchItem]


class SavedSearchResponse(CamelModel):
    search: SavedSearchItem
