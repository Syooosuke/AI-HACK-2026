"""users テーブルへのアクセス。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PUBLIC_TASK_STATUSES, Task, TaskStatus, User


def get(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def get_by_login_id(session: Session, login_id: str) -> User | None:
    """ログインIDでユーザーを引く。大文字小文字は区別しない（入力ゆれを吸収する）。"""
    stmt = select(User).where(func.lower(User.login_id) == login_id.lower())
    return session.scalars(stmt).first()


def create(session: Session, user: User) -> User:
    """ユーザーを登録する。commit は呼び出し側（サービス層）が行う。"""
    session.add(user)
    session.flush()
    return user


def list_all(session: Session) -> list[User]:
    """ユーザー一覧。信頼度の高い順に返す。"""
    stmt = select(User).order_by(User.trust_score.desc(), User.display_name)
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
