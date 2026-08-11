"""task_likes テーブルへのアクセス。"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Task, TaskLike


def get(session: Session, *, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskLike | None:
    stmt = select(TaskLike).where(TaskLike.user_id == user_id, TaskLike.task_id == task_id)
    return session.scalars(stmt).first()


def add(session: Session, *, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskLike:
    like = TaskLike(user_id=user_id, task_id=task_id)
    session.add(like)
    session.flush()
    return like


def remove(session: Session, *, user_id: uuid.UUID, task_id: uuid.UUID) -> int:
    """いいねを取り消す。削除した行数を返す（0なら元々押していない）。"""
    stmt = delete(TaskLike).where(TaskLike.user_id == user_id, TaskLike.task_id == task_id)
    return session.execute(stmt).rowcount or 0


def count_for_task(session: Session, task_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(TaskLike).where(TaskLike.task_id == task_id)
    return session.scalar(stmt) or 0


def liked_task_ids(
    session: Session, *, user_id: uuid.UUID, task_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """一覧表示用。渡した依頼のうち、自分がいいねしているものを返す。"""
    if not task_ids:
        return set()
    stmt = select(TaskLike.task_id).where(
        TaskLike.user_id == user_id, TaskLike.task_id.in_(task_ids)
    )
    return set(session.scalars(stmt))


def list_liked_tasks(session: Session, user_id: uuid.UUID) -> list[Task]:
    """いいねした依頼を、いいねした順（新しい順）に返す。"""
    stmt = (
        select(Task)
        .join(TaskLike, TaskLike.task_id == Task.id)
        .where(TaskLike.user_id == user_id)
        .order_by(TaskLike.created_at.desc())
    )
    return list(session.scalars(stmt))
