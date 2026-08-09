"""検品パイプラインの統括（docs/04-ai-pipeline.md 6節）。

`POST /api/submissions` の BackgroundTasks から呼ばれる。
**すべてのDB更新は単一トランザクションで行い、失敗時はロールバックする。**

処理順（docs/04-ai-pipeline.md 6節）:
  1. processing へ更新
  2. 機能C の C-1〜C-4, C-6（決定論的な位置・時刻チェック）
  3. 機能B（VLM検品）— 失敗時は error で終了
  4. 機能C の C-5（環境整合）を B の出力で判定
  5. reality_score を算出
  6. 合否判定 → 合格なら機能D（マスキング）→ 納品・報酬確定、不合格なら再撮影ループ
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.core.storage import StorageBackend, get_storage
from app.models import (
    AssignmentStatus,
    Submission,
    Task,
    TaskAssignment,
    TaskStatus,
    User,
    ValidationStatus,
)
from app.models.user import TRUST_SCORE_ON_APPROVED, TRUST_SCORE_ON_FAILED
from app.repositories import assignment_repo, submission_repo, task_repo
from app.schemas.ai import ImageValidationResult
from app.services import (
    image_validation,
    location_check,
    masking,
    payment_stub,
    task_service,
)
from app.services.orca_client import get_orca_client

logger = get_logger(__name__)


async def run_validation(submission_id: uuid.UUID) -> None:
    """1件の提出を検品する。例外は内部で処理し、呼び出し元へは伝播させない。"""
    factory = get_session_factory()
    storage = get_storage()
    orca = get_orca_client()

    with factory() as session:
        submission = submission_repo.get(session, submission_id)
        if submission is None:
            logger.warning("検品対象が見つかりません", extra={"submission_id": str(submission_id)})
            return
        submission.ai_validation_status = ValidationStatus.PROCESSING
        session.commit()

    try:
        with factory() as session:
            await _validate(session, submission_id=submission_id, storage=storage, orca=orca)
            session.commit()
    except Exception:
        logger.exception("検品処理が失敗しました", extra={"submission_id": str(submission_id)})
        _mark_error(submission_id)


async def _validate(
    session: Session, *, submission_id: uuid.UUID, storage: StorageBackend, orca: object
) -> None:
    settings = get_settings()
    submission = submission_repo.get(session, submission_id)
    if submission is None:
        return
    assignment = assignment_repo.get(session, submission.assignment_id)
    task = task_repo.get(session, submission.task_id)
    worker = session.get(User, submission.worker_id)
    if assignment is None or task is None or worker is None:
        return

    # 2. 決定論的な位置・時刻チェック（機能C の C-1〜C-4, C-6）
    location = location_check.run_deterministic_checks(task, submission)

    # 3. VLM検品（機能B）。失敗時は例外が伝播し、呼び出し元が error として記録する
    result = await image_validation.validate_image(
        session,
        task=task,
        submission=submission,
        orca=orca,  # type: ignore[arg-type]
        storage=storage,
    )

    # 4. C-5 環境整合（VLM の daylight_state を使う）
    location = location_check.apply_environment_check(location, submission, result.daylight_state)
    submission.location_check = location

    # 5. reality_score の算出（docs/04-ai-pipeline.md 4.2）
    submission.reality_score = location_check.compute_reality_score(
        location, worker_trust_score=worker.trust_score
    )

    # 6. 合否判定（docs/04-ai-pipeline.md 3.4）
    issues = [{"code": item.code, "message": item.message} for item in result.issues]
    if not location["within_tolerance"]:
        issues.append(
            {
                "code": "LOCATION_MISMATCH",
                "message": "依頼地点から離れすぎています。現地で撮影してください",
            }
        )
    if not location["timestamp_consistent"]:
        issues.append(
            {
                "code": "TIMESTAMP_MISMATCH",
                "message": "撮影時刻が確認できません。撮り直してください",
            }
        )

    approved = (
        result.score >= settings.submission_score_threshold
        and result.subject_present
        and location["within_tolerance"]
        and location["timestamp_consistent"]
    )

    submission.ai_score = result.score
    submission.ai_feedback = {
        "checks": {
            "subject_present": result.subject_present,
            "framing_ok": result.framing_ok,
            "sharpness_ok": result.sharpness_ok,
            "brightness_ok": result.brightness_ok,
        },
        "issues": [] if approved else issues,
        "summary": result.summary,
    }

    if approved:
        await _handle_approved(
            session,
            task=task,
            assignment=assignment,
            submission=submission,
            worker=worker,
            result=result,
            storage=storage,
        )
    else:
        _handle_rejected(
            session, task=task, assignment=assignment, submission=submission, worker=worker
        )

    logger.info(
        "検品が完了しました",
        extra={
            "submission_id": str(submission.id),
            "attempt_no": submission.attempt_no,
            "score": result.score,
            "reality_score": submission.reality_score,
            "flags": ",".join(location["flags"]) or "-",
            "result": "approved" if approved else "rejected",
        },
    )


async def _handle_approved(
    session: Session,
    *,
    task: Task,
    assignment: TaskAssignment,
    submission: Submission,
    worker: User,
    result: ImageValidationResult,
    storage: StorageBackend,
) -> None:
    settings = get_settings()

    # 6-1. 機能D（マスキング）。加工後の画像のみを配信用バケットへ置く。
    # **原本は STORAGE_BUCKET_RAW に残すが、APIレスポンスには一切含めない。**
    payload = await storage.download(
        bucket=settings.storage_bucket_raw, key=submission.raw_image_url
    )
    outcome = await masking.apply_masking(
        payload, orca=get_orca_client(), submission_id=submission.id
    )
    processed_key = f"{task.id}/{assignment.id}/{submission.attempt_no}.jpg"
    await storage.upload(
        bucket=settings.storage_bucket_processed,
        key=processed_key,
        data=outcome.image,
        content_type="image/jpeg",
    )
    submission.processed_image_url = processed_key
    submission.masking_result = outcome.result
    if outcome.skipped:
        logger.warning(
            "マスキングをスキップしたため加工されていない画像を配信します",
            extra={
                "submission_id": str(submission.id),
                "reason": outcome.result.get("reason") or "-",
            },
        )

    # 6-2〜6-5
    submission.ai_validation_status = ValidationStatus.APPROVED
    assignment.status = AssignmentStatus.APPROVED
    assignment.completed_at = datetime.now(UTC)
    task.approved_worker_count += 1
    if task.approved_worker_count >= task.required_worker_count:
        task.status = TaskStatus.COMPLETED
    worker.apply_trust_score_delta(TRUST_SCORE_ON_APPROVED)
    worker.completed_task_count += 1

    # 6-6. 決済スタブ（D-03）。charge / payout を記録するだけで実決済は行わない
    payment_stub.record_settlement(session, task=task, submission=submission)

    # 6-7. 合格提出の要約を結合して依頼全体の結果要約にする。
    # 先に flush して、今回の提出が approved としてクエリに含まれる状態にする。
    session.flush()
    task.result_summary = _combine_result_summary(session, task)
    session.flush()


def _handle_rejected(
    session: Session,
    *,
    task: Task,
    assignment: TaskAssignment,
    submission: Submission,
    worker: User,
) -> None:
    settings = get_settings()
    submission.ai_validation_status = ValidationStatus.REJECTED

    if assignment.retake_count < settings.max_retake_count:
        # 再撮影を許可する（retake_count を進めて accepted へ戻す）
        assignment.retake_count += 1
        assignment.status = AssignmentStatus.ACCEPTED
    else:
        # 上限超過。枠を他ワーカーへ再開放する（D-08）
        assignment.status = AssignmentStatus.FAILED
        assignment.completed_at = datetime.now(UTC)
        worker.apply_trust_score_delta(TRUST_SCORE_ON_FAILED)
        session.flush()
        task_service.reopen_if_slot_available(session, task)
    session.flush()


def _mark_error(submission_id: uuid.UUID) -> None:
    """検品失敗時の後始末。**再撮影回数は消費しない**（ワーカーの責任ではないため）。"""
    session_factory = get_session_factory()
    with session_factory() as session:
        submission = submission_repo.get(session, submission_id)
        if submission is None:
            return
        submission.ai_validation_status = ValidationStatus.ERROR
        submission.ai_feedback = {
            "checks": {},
            "issues": [
                {
                    "code": "OTHER",
                    "message": "システム側の問題で検品できませんでした。もう一度送信してください",
                }
            ],
            "summary": "検品処理に失敗しました。",
        }
        assignment = assignment_repo.get(session, submission.assignment_id)
        if assignment is not None and assignment.status is AssignmentStatus.SUBMITTED:
            assignment.status = AssignmentStatus.ACCEPTED
        session.commit()


def _combine_result_summary(session: Session, task: Task) -> str:
    """合格済み提出の要約を結合する（docs/04-ai-pipeline.md 6節 6-7）。"""
    summaries: list[str] = []
    for submission, _worker in submission_repo.list_approved_by_task(session, task.id):
        summary = (submission.ai_feedback or {}).get("summary")
        if summary:
            summaries.append(summary)
    return " / ".join(dict.fromkeys(summaries))
