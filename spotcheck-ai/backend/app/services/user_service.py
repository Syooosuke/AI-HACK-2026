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
from app.schemas.task import TaskOwner
from app.schemas.user import (
    PublicProfile,
    RequesterStats,
    WorkerStats,
)
from app.services import avatar_service


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
        avatar_url=avatar_service.public_url(user),
        joined_at=user.created_at,
        as_requester=RequesterStats(
            published_task_count=counts.published,
            completed_task_count=counts.completed,
            completion_rate=_completion_rate(counts.published, counts.completed),
        ),
        as_worker=WorkerStats(
            # 0〜100 のまま返す。画面はゲージで表示する（PR #11 の方針）
            trust_score=float(user.trust_score),
            approved_submission_count=user.completed_task_count,
        ),
    )


def build_task_owner(session: Session, owner: User) -> TaskOwner:
    """依頼詳細に載せる依頼主。プロフィールへ遷移せずに判断できる最小限も添える。

    `TaskOwner` は依頼詳細（docs/03-api.md 3.4）で既に使われているため、
    公開プロフィールへの導線は**新しいフィールドを増やさずここを拡張して**実現する。
    """
    counts = user_repo.requester_counts(session, owner.id)
    return TaskOwner(
        id=owner.id,
        display_name=owner.display_name,
        trust_score=float(owner.trust_score),
        completed_task_count=owner.completed_task_count,
        avatar_url=avatar_service.public_url(owner),
        published_task_count=counts.published,
        completion_rate=_completion_rate(counts.published, counts.completed),
    )
