"""ユーザー関連のスキーマ。"""

from __future__ import annotations

import uuid

from app.models.enums import UserRole
from app.schemas.common import CamelModel

#: 表示用の星評価は5段階に換算する（docs/03-api.md 3.8）
TRUST_SCORE_TO_STARS_DIVISOR = 20


class DemoUser(CamelModel):
    id: uuid.UUID
    role: UserRole
    display_name: str
    trust_score: float
    completed_task_count: int
    avatar_url: str | None = None


class DemoUserListResponse(CamelModel):
    users: list[DemoUser]


class WorkerSummary(CamelModel):
    """画面⑩のワーカー評価表示用。`trust_score` は5段階へ換算した値。"""

    display_name: str
    trust_score: float
    avatar_url: str | None = None
