"""saved_searches テーブルへのアクセス。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SavedSearch


def get(session: Session, search_id: uuid.UUID) -> SavedSearch | None:
    return session.get(SavedSearch, search_id)


def list_by_user(session: Session, user_id: uuid.UUID) -> list[SavedSearch]:
    stmt = (
        select(SavedSearch)
        .where(SavedSearch.user_id == user_id)
        .order_by(SavedSearch.created_at.desc())
    )
    return list(session.scalars(stmt))


def count_by_user(session: Session, user_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(SavedSearch).where(SavedSearch.user_id == user_id)
    return session.scalar(stmt) or 0


def create(session: Session, search: SavedSearch) -> SavedSearch:
    session.add(search)
    session.flush()
    return search


def delete(session: Session, search: SavedSearch) -> None:
    session.delete(search)
    session.flush()
