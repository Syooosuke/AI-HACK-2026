"""公開プロフィールの組み立て（docs/03-api.md 3.4.1）。

**公開範囲の判断はこのモジュールに集約する。** ルーターやスキーマに散らさないこと。
`email` / `login_id` などの非公開項目は、ここで組み立てない限り外に出ない。
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.models import User
from app.repositories import user_repo
from app.schemas.user import (
    TRUST_SCORE_TO_STARS_DIVISOR,
    PublicProfile,
    RequesterStats,
    RequesterSummary,
    WorkerStats,
)


def _stars(user: User) -> float:
    """信頼度スコアを5段階へ換算する（docs/03-api.md 3.8 と同じ換算）。"""
    return round(float(user.trust_score) / TRUST_SCORE_TO_STARS_DIVISOR, 1)


def _completion_rate(published: int, completed: int) -> float | None:
    """完了率。母数が0のときは「実績なし」を表すため null を返す。"""
    if published == 0:
        return None
    return round(completed / published, 2)


def _require_user(session: Session, user_id: uuid.UUID) -> User:
    user = user_repo.get(session, user_id)
    if user is None:
        raise NotFound("指定されたユーザーが見つかりません。", code="USER_NOT_FOUND")
    return user


def build_public_profile(session: Session, user_id: uuid.UUID) -> PublicProfile:
    """閲覧専用プロフィール。依頼者とワーカーの両面を返す。

    ロールは参照しない（1アカウントが両方の役割を持ちうる）。実績が0でもセクションは返し、
    表示側で「まだ実績がありません」と出す。
    """
    user = _require_user(session, user_id)
    counts = user_repo.requester_counts(session, user_id)

    return PublicProfile(
        id=user.id,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        joined_at=user.created_at,
        as_requester=RequesterStats(
            published_task_count=counts.published,
            completed_task_count=counts.completed,
            completion_rate=_completion_rate(counts.published, counts.completed),
        ),
        as_worker=WorkerStats(
            trust_score=_stars(user),
            approved_submission_count=user.completed_task_count,
        ),
    )


def build_requester_summary(session: Session, user_id: uuid.UUID) -> RequesterSummary:
    """画面⑤の依頼者行に出す要約。プロフィールへ遷移せずに判断できる最小限だけ返す。"""
    user = _require_user(session, user_id)
    counts = user_repo.requester_counts(session, user_id)
    return RequesterSummary(
        id=user.id,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        published_task_count=counts.published,
        completion_rate=_completion_rate(counts.published, counts.completed),
    )
