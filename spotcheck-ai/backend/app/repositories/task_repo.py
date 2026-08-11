"""tasks / task_reference_images テーブルへのアクセス。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Task, TaskReferenceImage, TaskStatus

#: 近傍検索で掲示板に出す status（docs/03-api.md 3.3）
BOARD_VISIBLE_STATUSES = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)


def create(session: Session, task: Task) -> Task:
    session.add(task)
    session.flush()
    return task


def get(session: Session, task_id: uuid.UUID) -> Task | None:
    return session.get(Task, task_id)


def get_for_update(session: Session, task_id: uuid.UUID) -> Task | None:
    """受注処理用に行ロックを取得する（docs/02-database.md 2.4）。"""
    stmt = select(Task).where(Task.id == task_id).with_for_update()
    return session.scalars(stmt).one_or_none()


def list_by_client(session: Session, client_id: uuid.UUID) -> list[Task]:
    stmt = select(Task).where(Task.client_id == client_id).order_by(Task.created_at.desc())
    return list(session.scalars(stmt))


def find_board_tasks_in_box(
    session: Session,
    *,
    min_lat: float,
    max_lat: float,
    min_lng: float,
    max_lng: float,
    now: datetime,
) -> list[Task]:
    """バウンディングボックスで粗く絞る。正確な距離判定は呼び出し側で Haversine を使う。"""
    stmt = select(Task).where(
        Task.status.in_(BOARD_VISIBLE_STATUSES),
        Task.deadline_at > now,
        Task.location_lat.between(min_lat, max_lat),
        Task.location_lng.between(min_lng, max_lng),
    )
    return list(session.scalars(stmt))


def find_expired(session: Session, now: datetime) -> list[Task]:
    """期限を過ぎた未終了タスク（docs/03-api.md 4.1 / Phase 6 のジョブが使う）。"""
    stmt = select(Task).where(
        Task.deadline_at < now,
        Task.status.in_(
            (
                TaskStatus.OPEN,
                TaskStatus.IN_PROGRESS,
                TaskStatus.NEEDS_INFO,
                TaskStatus.SCREENING,
            )
        ),
    )
    return list(session.scalars(stmt))


def add_reference_image(
    session: Session, *, task_id: uuid.UUID, image_url: str, sort_order: int
) -> TaskReferenceImage:
    image = TaskReferenceImage(task_id=task_id, image_url=image_url, sort_order=sort_order)
    session.add(image)
    session.flush()
    return image


def increment_view_count(session: Session, task_id: uuid.UUID) -> int:
    """閲覧数を1増やして新しい値を返す。同時アクセスでも取りこぼさないようSQLで加算する。"""
    stmt = (
        update(Task)
        .where(Task.id == task_id)
        .values(view_count=Task.view_count + 1)
        .returning(Task.view_count)
    )
    return session.execute(stmt).scalar_one()
