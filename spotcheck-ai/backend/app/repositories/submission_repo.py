"""submissions テーブルへのアクセス。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Submission, User, ValidationStatus


def create(session: Session, submission: Submission) -> Submission:
    session.add(submission)
    session.flush()
    return submission


def get(session: Session, submission_id: uuid.UUID) -> Submission | None:
    return session.get(Submission, submission_id)


def latest_by_assignment(session: Session, assignment_id: uuid.UUID) -> Submission | None:
    stmt = (
        select(Submission)
        .where(Submission.assignment_id == assignment_id)
        .order_by(Submission.attempt_no.desc())
        .limit(1)
    )
    return session.scalars(stmt).one_or_none()


def list_approved_by_task(session: Session, task_id: uuid.UUID) -> list[tuple[Submission, User]]:
    """合格済み提出のみを返す（docs/03-api.md 3.8。D-07により随時追加される）。"""
    stmt = (
        select(Submission, User)
        .join(User, User.id == Submission.worker_id)
        .where(
            Submission.task_id == task_id,
            Submission.ai_validation_status == ValidationStatus.APPROVED,
        )
        .order_by(Submission.created_at)
    )
    return [(submission, worker) for submission, worker in session.execute(stmt)]
