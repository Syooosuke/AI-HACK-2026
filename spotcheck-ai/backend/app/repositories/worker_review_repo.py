"""ワーカー評価のDBアクセス。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Task, WorkerReview


def get_by_submission(session: Session, submission_id: uuid.UUID) -> WorkerReview | None:
    return session.scalars(
        select(WorkerReview).where(WorkerReview.submission_id == submission_id)
    ).one_or_none()


def create(session: Session, review: WorkerReview) -> WorkerReview:
    session.add(review)
    session.flush()
    return review


@dataclass(frozen=True)
class ReviewStats:
    average: float | None
    count: int


def stats_for_worker(session: Session, worker_id: uuid.UUID) -> ReviewStats:
    average, count = session.execute(
        select(func.avg(WorkerReview.rating), func.count()).where(
            WorkerReview.worker_id == worker_id
        )
    ).one()
    return ReviewStats(average=round(float(average), 1) if average is not None else None, count=count)


def list_for_worker(session: Session, worker_id: uuid.UUID) -> list[tuple[WorkerReview, str]]:
    """本人向けの評価一覧。依頼者はjoinせず匿名性を保つ。"""
    stmt = (
        select(WorkerReview, Task.title)
        .join(Task, Task.id == WorkerReview.task_id)
        .where(WorkerReview.worker_id == worker_id)
        .order_by(WorkerReview.created_at.desc())
    )
    return [(review, task_title) for review, task_title in session.execute(stmt)]
