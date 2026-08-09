"""提出（submission）に関する業務ロジック（docs/03-api.md 3.6〜3.8）。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import Conflict, Forbidden, NotFound, ValidationError
from app.core.logging import get_logger
from app.core.storage import StorageBackend
from app.models import (
    AssignmentStatus,
    Submission,
    Task,
    TaskAssignment,
    User,
    UserRole,
    ValidationStatus,
)
from app.repositories import assignment_repo, submission_repo, task_repo
from app.schemas.submission import (
    Issue,
    RetakeInfo,
    SubmissionChecks,
    SubmissionCreated,
    SubmissionCreateResponse,
    SubmissionStatusResponse,
    TaskResultItem,
    TaskResultsResponse,
)
from app.schemas.user import TRUST_SCORE_TO_STARS_DIVISOR, WorkerSummary
from app.services.exif import extract_exif
from app.services.uploads import extension_for, read_and_validate_image

logger = get_logger(__name__)


@dataclass
class SubmissionInput:
    assignment_id: uuid.UUID
    captured_lat: float
    captured_lng: float
    captured_at: datetime
    captured_accuracy_m: float | None = None
    device_info_raw: str | None = None


async def create_submission(
    session: Session,
    *,
    worker: User,
    data: SubmissionInput,
    image: UploadFile,
    storage: StorageBackend,
) -> SubmissionCreateResponse:
    """画像を保存し、検品前の submission を作成する（実際の検品はBackgroundTasksで行う）。"""
    settings = get_settings()

    assignment = assignment_repo.get(session, data.assignment_id)
    if assignment is None:
        raise NotFound("指定された受注が見つかりません。", code="ASSIGNMENT_NOT_FOUND")
    if assignment.worker_id != worker.id:
        raise Forbidden("他のワーカーの受注には提出できません。")
    if assignment.status is not AssignmentStatus.ACCEPTED:
        raise Conflict("この受注は現在提出できる状態ではありません。", code="INVALID_STATE")
    if assignment.retake_count > settings.max_retake_count:
        raise Conflict("再撮影の上限に達しています。", code="RETAKE_LIMIT_EXCEEDED")

    captured_at = _ensure_aware(data.captured_at)
    elapsed = abs((datetime.now(UTC) - captured_at).total_seconds())
    if elapsed > settings.capture_freshness_seconds:
        raise ValidationError(
            "撮影から時間が経過しすぎています。アプリ内カメラで撮影し直してください。",
            details={"field": "capturedAt", "elapsedSeconds": int(elapsed)},
        )

    task = task_repo.get(session, assignment.task_id)
    if task is None:  # 外部キー制約上ありえないが、念のため
        raise NotFound("指定された依頼が見つかりません。", code="TASK_NOT_FOUND")

    payload, content_type = await read_and_validate_image(image, field="image")
    attempt_no = assignment.retake_count + 1
    key = f"{task.id}/{assignment.id}/{attempt_no}.{extension_for(content_type)}"
    await storage.upload(
        bucket=settings.storage_bucket_raw,
        key=key,
        data=payload,
        content_type=content_type,
    )

    submission = Submission(
        assignment_id=assignment.id,
        task_id=task.id,
        worker_id=worker.id,
        attempt_no=attempt_no,
        raw_image_url=key,
        captured_lat=data.captured_lat,
        captured_lng=data.captured_lng,
        captured_accuracy_m=data.captured_accuracy_m,
        captured_at=captured_at,
        device_info=_parse_device_info(data.device_info_raw),
        # EXIFは補助的な検証材料。抽出に失敗しても提出は通す（D-02）
        exif_data=extract_exif(payload),
        ai_validation_status=ValidationStatus.PENDING,
    )
    submission_repo.create(session, submission)

    assignment.status = AssignmentStatus.SUBMITTED
    session.flush()

    logger.info(
        "提出を受け付けました",
        extra={
            "submission_id": str(submission.id),
            "assignment_id": str(assignment.id),
            "attempt_no": attempt_no,
        },
    )
    return SubmissionCreateResponse(
        submission=SubmissionCreated(
            id=submission.id,
            attempt_no=submission.attempt_no,
            ai_validation_status=submission.ai_validation_status,
        ),
        poll_url=f"/api/submissions/{submission.id}",
    )


async def get_submission_status(
    session: Session, *, user: User, submission_id: uuid.UUID, storage: StorageBackend
) -> SubmissionStatusResponse:
    """検品状況のポーリング（docs/03-api.md 3.7）。原本URLは絶対に含めない。"""
    settings = get_settings()
    submission = submission_repo.get(session, submission_id)
    if submission is None:
        raise NotFound("指定された提出が見つかりません。", code="SUBMISSION_NOT_FOUND")

    assignment = assignment_repo.get(session, submission.assignment_id)
    task = task_repo.get(session, submission.task_id)
    if assignment is None or task is None:
        raise NotFound("指定された提出が見つかりません。", code="SUBMISSION_NOT_FOUND")

    if user.role is UserRole.WORKER and submission.worker_id != user.id:
        raise Forbidden("他のワーカーの提出は参照できません。")
    if user.role is UserRole.CLIENT and task.client_id != user.id:
        raise Forbidden("他のクライアントの依頼の提出は参照できません。")

    feedback = submission.ai_feedback or {}
    checks = feedback.get("checks", {})
    location = submission.location_check or {}
    issues = [
        Issue(code=item["code"], message=item["message"]) for item in feedback.get("issues", [])
    ]

    retake_allowed = (
        submission.ai_validation_status is ValidationStatus.REJECTED
        and assignment.status is AssignmentStatus.ACCEPTED
    ) or submission.ai_validation_status is ValidationStatus.ERROR

    return SubmissionStatusResponse(
        id=submission.id,
        attempt_no=submission.attempt_no,
        ai_validation_status=submission.ai_validation_status,
        ai_score=submission.ai_score,
        reality_score=submission.reality_score,
        processed_image_url=await _signed_processed_url(storage, submission),
        checks=SubmissionChecks(
            framing_ok=bool(checks.get("framing_ok")),
            subject_present=bool(checks.get("subject_present")),
            location_verified=bool(
                location.get("within_tolerance") and location.get("timestamp_consistent")
            ),
            privacy_masked=bool((submission.masking_result or {}).get("regions")),
        ),
        issues=issues,
        retake=RetakeInfo(
            allowed=retake_allowed,
            remaining=max(0, settings.max_retake_count - assignment.retake_count),
        ),
        assignment_status=assignment.status,
    )


async def get_task_results(
    session: Session, *, client: User, task_id: uuid.UUID, storage: StorageBackend
) -> TaskResultsResponse:
    """合格済み提出の一覧（docs/03-api.md 3.8）。client のみ。"""
    task = task_repo.get(session, task_id)
    if task is None:
        raise NotFound("指定された依頼が見つかりません。", code="TASK_NOT_FOUND")
    if task.client_id != client.id:
        raise Forbidden("他のクライアントの依頼は参照できません。")

    rows = submission_repo.list_approved_by_task(session, task_id)
    results: list[TaskResultItem] = []
    for submission, worker in rows:
        feedback = submission.ai_feedback or {}
        results.append(
            TaskResultItem(
                submission_id=submission.id,
                processed_image_url=await _signed_processed_url(storage, submission),
                captured_at=submission.captured_at,
                captured_lat=submission.captured_lat,
                captured_lng=submission.captured_lng,
                location_label=task.location_address,
                reality_score=submission.reality_score,
                ai_summary=feedback.get("summary"),
                location_check=submission.location_check,
                worker=WorkerSummary(
                    display_name=worker.display_name,
                    trust_score=round(float(worker.trust_score) / TRUST_SCORE_TO_STARS_DIVISOR, 1),
                    avatar_url=worker.avatar_url,
                ),
            )
        )

    return TaskResultsResponse(
        task_id=task.id,
        status=task.status,
        result_summary=task.result_summary,
        approved_count=task.approved_worker_count,
        required_worker_count=task.required_worker_count,
        results=results,
    )


# ----------------------------------------------------------------------
# 内部ヘルパー
# ----------------------------------------------------------------------
async def _signed_processed_url(storage: StorageBackend, submission: Submission) -> str | None:
    """マスキング済み画像の署名URLのみを返す。**原本は絶対に署名しない。**"""
    if not submission.processed_image_url:
        return None
    return await storage.create_signed_url(
        bucket=get_settings().storage_bucket_processed, key=submission.processed_image_url
    )


def _parse_device_info(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # 端末情報は補助データのため、壊れていても提出自体は通す
        return {"raw": raw[:500]}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def assignment_for(session: Session, submission: Submission) -> TaskAssignment:
    assignment = assignment_repo.get(session, submission.assignment_id)
    if assignment is None:
        raise NotFound("指定された受注が見つかりません。", code="ASSIGNMENT_NOT_FOUND")
    return assignment


def task_for(session: Session, submission: Submission) -> Task:
    task = task_repo.get(session, submission.task_id)
    if task is None:
        raise NotFound("指定された依頼が見つかりません。", code="TASK_NOT_FOUND")
    return task
