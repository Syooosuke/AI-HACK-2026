"""users テーブルへのアクセス。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def list_all(session: Session) -> list[User]:
    """デモユーザー一覧（画面切替用）。クライアントを先に、次にワーカーを信頼度降順で返す。"""
    stmt = select(User).order_by(User.role, User.trust_score.desc(), User.display_name)
    return list(session.scalars(stmt))
