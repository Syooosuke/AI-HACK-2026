"""ユーザー関連のスキーマ。ログイン中ユーザーの表現は `app/schemas/auth.py` にある。"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.schemas.common import CamelModel


class WorkerSummary(CamelModel):
    """画面⑨⑩のワーカー表示用。

    `trust_score` は 0〜100 のまま返す（画面はゲージで表示するため、
    5段階への換算は行わない）。`avatar_url` はアバターの配信URL。
    """

    id: uuid.UUID
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
    """ワーカーとしての実績。

    `trust_score` は `WorkerSummary` と同じく 0〜100 のまま返す
    （画面はゲージで表示するため、5段階への換算は行わない）。
    """

    trust_score: float
    approved_submission_count: int
    average_rating: float | None = None
    review_count: int = 0


class PublicProfile(CamelModel):
    id: uuid.UUID
    display_name: str
    avatar_url: str | None = None
    joined_at: datetime
    as_requester: RequesterStats
    as_worker: WorkerStats
