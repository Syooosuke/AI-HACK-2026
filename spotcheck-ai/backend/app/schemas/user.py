"""ユーザー関連のスキーマ。"""

from __future__ import annotations

import uuid
from datetime import datetime

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


# ----------------------------------------------------------------------
# 公開プロフィール（docs/03-api.md 3.4.1）
#
# **email / login_id は絶対に含めない。** 追加する項目は公開してよいか個別に判断する。
# ----------------------------------------------------------------------
class RequesterStats(CamelModel):
    """依頼者としての実績。母数は公開された依頼のみ。"""

    published_task_count: int
    completed_task_count: int
    #: completed / published。母数0なら null
    completion_rate: float | None = None


class WorkerStats(CamelModel):
    """ワーカーとしての実績。`trust_score` は5段階へ換算した値。"""

    trust_score: float
    approved_submission_count: int


class PublicProfile(CamelModel):
    id: uuid.UUID
    display_name: str
    avatar_url: str | None = None
    joined_at: datetime
    as_requester: RequesterStats
    as_worker: WorkerStats


class RequesterSummary(CamelModel):
    """画面⑤に出す依頼者の要約。プロフィールへの導線に使う。"""

    id: uuid.UUID
    display_name: str
    avatar_url: str | None = None
    published_task_count: int
    completion_rate: float | None = None
