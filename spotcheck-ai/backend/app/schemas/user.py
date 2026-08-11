"""ユーザー関連のスキーマ。ログイン中ユーザーの表現は `app/schemas/auth.py` にある。"""

from __future__ import annotations

from app.schemas.common import CamelModel


class WorkerSummary(CamelModel):
    """画面⑨⑩のワーカー表示用。

    `trust_score` は 0〜100 のまま返す（画面はゲージで表示するため、
    5段階への換算は行わない）。`avatar_url` はアバターの配信URL。
    """

    display_name: str
    trust_score: float
    avatar_url: str | None = None
