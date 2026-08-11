"""ユーザー関連のスキーマ。ログイン中ユーザーの表現は `app/schemas/auth.py` にある。"""

from __future__ import annotations

from app.schemas.common import CamelModel

#: 表示用の星評価は5段階に換算する（docs/03-api.md 3.8）
TRUST_SCORE_TO_STARS_DIVISOR = 20


class WorkerSummary(CamelModel):
    """画面⑩のワーカー評価表示用。`trust_score` は5段階へ換算した値。"""

    display_name: str
    trust_score: float
    avatar_url: str | None = None
