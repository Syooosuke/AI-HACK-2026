"""users テーブルへのアクセス。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PUBLIC_TASK_STATUSES, Task, TaskStatus, User


def get(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def list_all(session: Session) -> list[User]:
    """デモユーザー一覧（画面切替用）。クライアントを先に、次にワーカーを信頼度降順で返す。"""
    stmt = select(User).order_by(User.role, User.trust_score.desc(), User.display_name)
    return list(session.scalars(stmt))


@dataclass(frozen=True)
class RequesterCounts:
    """依頼者としての実績。母数は公開された依頼のみ（PUBLIC_TASK_STATUSES）。"""

    published: int
    completed: int


def requester_counts(session: Session, user_id: uuid.UUID) -> RequesterCounts:
    """公開した依頼数と完了した依頼数を1クエリで取得する。

    却下・審査中・情報補足待ちの依頼は母数に含めない
    （docs/03-api.md 3.4.1）。
    """
    stmt = select(
        func.count(),
        func.count().filter(Task.status == TaskStatus.COMPLETED),
    ).where(Task.client_id == user_id, Task.status.in_(PUBLIC_TASK_STATUSES))
    published, completed = session.execute(stmt).one()
    return RequesterCounts(published=published or 0, completed=completed or 0)
