"""task_assignments テーブルへのアクセス。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ACTIVE_ASSIGNMENT_STATUSES, AssignmentStatus, Task, TaskAssignment


def create(session: Session, *, task_id: uuid.UUID, worker_id: uuid.UUID) -> TaskAssignment:
    assignment = TaskAssignment(task_id=task_id, worker_id=worker_id)
    session.add(assignment)
    session.flush()
    return assignment


def get(session: Session, assignment_id: uuid.UUID) -> TaskAssignment | None:
    return session.get(TaskAssignment, assignment_id)


def get_by_task_and_worker(
    session: Session, *, task_id: uuid.UUID, worker_id: uuid.UUID
) -> TaskAssignment | None:
    stmt = select(TaskAssignment).where(
        TaskAssignment.task_id == task_id, TaskAssignment.worker_id == worker_id
    )
    return session.scalars(stmt).one_or_none()


def count_active(session: Session, task_id: uuid.UUID) -> int:
    """枠を占有している assignment 数（accepted / submitted / approved）。"""
    stmt = select(func.count()).where(
        TaskAssignment.task_id == task_id,
        TaskAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
    )
    return session.scalar(stmt) or 0


def count_active_by_task(session: Session, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """複数タスク分の使用中枠数をまとめて取得する（一覧APIのN+1を避ける）。"""
    if not task_ids:
        return {}
    stmt = (
        select(TaskAssignment.task_id, func.count())
        .where(
            TaskAssignment.task_id.in_(task_ids),
            TaskAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
        .group_by(TaskAssignment.task_id)
    )
    return {task_id: count for task_id, count in session.execute(stmt)}


def list_active_by_task(session: Session, task_id: uuid.UUID) -> list[TaskAssignment]:
    stmt = (
        select(TaskAssignment)
        .where(
            TaskAssignment.task_id == task_id,
            TaskAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
        .order_by(TaskAssignment.accepted_at)
    )
    return list(session.scalars(stmt))


def list_by_task(session: Session, task_id: uuid.UUID) -> list[TaskAssignment]:
    stmt = (
        select(TaskAssignment)
        .where(TaskAssignment.task_id == task_id)
        .order_by(TaskAssignment.accepted_at)
    )
    return list(session.scalars(stmt))


def list_by_worker_with_task(
    session: Session, worker_id: uuid.UUID
) -> list[tuple[TaskAssignment, Task]]:
    """ワーカーの受注一覧。終了済み（failed / cancelled / expired）も含めて新しい順に返す。"""
    stmt = (
        select(TaskAssignment, Task)
        .join(Task, Task.id == TaskAssignment.task_id)
        .where(TaskAssignment.worker_id == worker_id)
        .order_by(TaskAssignment.accepted_at.desc())
    )
    return [(assignment, task) for assignment, task in session.execute(stmt)]


def list_unfinished_by_task(session: Session, task_id: uuid.UUID) -> list[TaskAssignment]:
    """期限切れ処理の対象（accepted / submitted）。"""
    stmt = select(TaskAssignment).where(
        TaskAssignment.task_id == task_id,
        TaskAssignment.status.in_((AssignmentStatus.ACCEPTED, AssignmentStatus.SUBMITTED)),
    )
    return list(session.scalars(stmt))
