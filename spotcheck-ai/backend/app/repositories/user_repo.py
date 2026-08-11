"""users テーブルへのアクセス。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User


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
