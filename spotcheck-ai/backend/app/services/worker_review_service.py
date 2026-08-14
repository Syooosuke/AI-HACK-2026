"""依頼者によるワーカー評価の業務ロジック。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, Forbidden, NotFound
from app.models import User, ValidationStatus, WorkerReview
from app.repositories import submission_repo, task_repo, worker_review_repo
from app.schemas.worker_review import (
    ReceivedWorkerReview,
    ReceivedWorkerReviewList,
    WorkerReviewCreate,
    WorkerReviewResponse,
)


def _response(review: WorkerReview) -> WorkerReviewResponse:
    return WorkerReviewResponse(
        id=review.id,
        submission_id=review.submission_id,
        worker_id=review.worker_id,
        rating=review.rating,
        tags=review.tags,
        comment=review.comment,
        created_at=review.created_at,
    )


def create_review(
    session: Session,
    *,
    reviewer: User,
    submission_id: uuid.UUID,
    payload: WorkerReviewCreate,
) -> WorkerReviewResponse:
    submission = submission_repo.get(session, submission_id)
    if submission is None:
        raise NotFound("指定された提出が見つかりません。", code="SUBMISSION_NOT_FOUND")
    task = task_repo.get(session, submission.task_id)
    if task is None:
        raise NotFound("指定された依頼が見つかりません。", code="TASK_NOT_FOUND")
    if task.client_id != reviewer.id:
        raise Forbidden("この提出を評価できるのは依頼者本人だけです。")
    if submission.ai_validation_status is not ValidationStatus.APPROVED:
        raise Conflict("合格済みの提出だけを評価できます。", code="INVALID_STATE")
    if worker_review_repo.get_by_submission(session, submission_id) is not None:
        raise Conflict("この提出はすでに評価済みです。", code="REVIEW_ALREADY_EXISTS")

    review = worker_review_repo.create(
        session,
        WorkerReview(
            submission_id=submission.id,
            task_id=task.id,
            reviewer_id=reviewer.id,
            worker_id=submission.worker_id,
            rating=payload.rating,
            tags=list(payload.tags),
            comment=payload.comment,
        ),
    )
    return _response(review)


def list_received_reviews(session: Session, *, worker: User) -> ReceivedWorkerReviewList:
    rows = worker_review_repo.list_for_worker(session, worker.id)
    stats = worker_review_repo.stats_for_worker(session, worker.id)
    return ReceivedWorkerReviewList(
        reviews=[
            ReceivedWorkerReview(
                id=review.id,
                submission_id=review.submission_id,
                task_id=review.task_id,
                task_title=task_title,
                rating=review.rating,
                tags=review.tags,
                comment=review.comment,
                created_at=review.created_at,
            )
            for review, task_title in rows
        ],
        average_rating=stats.average,
        review_count=stats.count,
    )
