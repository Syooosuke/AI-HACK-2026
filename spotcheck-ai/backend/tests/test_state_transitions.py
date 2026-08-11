"""状態遷移のテスト（docs/06-phases.md Phase 1 完了条件）。

最低限のカバー範囲: 受注競合 / 再撮影上限 / 期限超過。
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.exceptions import AppError, Conflict
from app.core.storage import get_storage
from app.models import AssignmentStatus, Submission, TaskStatus, User, ValidationStatus
from app.repositories import assignment_repo, submission_repo
from app.services import masking, submission_pipeline, task_service
from tests.conftest import make_assignment, make_task, store_raw_image


# ----------------------------------------------------------------------
# 受注競合
# ----------------------------------------------------------------------
def test_second_worker_gets_task_full(session: Session, users: dict[str, User]) -> None:
    """1枠の依頼を2人が順に受注すると、2人目は 409 TASK_FULL になる。"""
    task = make_task(session, client=users["client"])

    task_service.accept_task(session, worker=users["worker"], task_id=task.id)
    session.commit()

    with pytest.raises(Conflict) as exc:
        task_service.accept_task(session, worker=users["worker2"], task_id=task.id)
    assert exc.value.code == "TASK_FULL"
    assert exc.value.status_code == 409


def test_concurrent_accept_allows_only_one(session: Session, users: dict[str, User]) -> None:
    """同時受注でも枠を超えない（tasks の SELECT FOR UPDATE による直列化）。"""
    task = make_task(session, client=users["client"], required_worker_count=1)
    task_id = task.id
    factory = get_session_factory()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(worker_id: uuid.UUID) -> None:
        with factory() as db:
            worker = db.get(User, worker_id)
            assert worker is not None
            barrier.wait(timeout=5)
            try:
                task_service.accept_task(db, worker=worker, task_id=task_id)
                db.commit()
                result = "accepted"
            except AppError as exc:
                db.rollback()
                result = exc.code
            with lock:
                outcomes.append(result)

    threads = [
        threading.Thread(target=attempt, args=(users["worker"].id,)),
        threading.Thread(target=attempt, args=(users["worker2"].id,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert sorted(outcomes) == ["TASK_FULL", "accepted"], outcomes
    assert assignment_repo.count_active(session, task_id) == 1


# ----------------------------------------------------------------------
# 再撮影ループ
# ----------------------------------------------------------------------
def _submit_and_validate(session: Session, *, task, assignment, worker: User) -> Submission:
    """1回分の提出と検品パイプラインを実行する。"""
    attempt_no = assignment.retake_count + 1
    key = f"{task.id}/{assignment.id}/{attempt_no}.jpg"
    store_raw_image(key)
    now = datetime.now(UTC)
    submission = Submission(
        assignment_id=assignment.id,
        task_id=task.id,
        worker_id=worker.id,
        attempt_no=attempt_no,
        raw_image_url=key,
        captured_lat=task.location_lat,
        captured_lng=task.location_lng,
        captured_at=now,
        received_at=now,
        ai_validation_status=ValidationStatus.PENDING,
    )
    submission_repo.create(session, submission)
    assignment.status = AssignmentStatus.SUBMITTED
    session.commit()

    asyncio.run(submission_pipeline.run_validation(submission.id))

    session.expire_all()
    return submission


def test_retake_loop_first_reject_then_approve(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """スタブは奇数回目を不合格にするため、1回目不合格 → 2回目合格になる。"""
    # YOLOの重みは .gitignore 対象で、クローン直後やワークツリーには存在しない。
    # 重みの有無でマスキングの skipped が変わりテストが環境依存になるため、
    # 検出器を差し替えて「重みはあるが検出0件」の状態に固定する。
    monkeypatch.setattr(masking, "load_models", lambda: masking._Models("general", "face", None))
    monkeypatch.setattr(masking, "_detect", lambda *_args, **_kwargs: [])

    task = make_task(session, client=users["client"])
    assignment = make_assignment(session, task=task, worker=users["worker"])

    first = _submit_and_validate(session, task=task, assignment=assignment, worker=users["worker"])
    assert first.ai_validation_status is ValidationStatus.REJECTED
    assert first.ai_score == 45
    assert assignment.status is AssignmentStatus.ACCEPTED
    assert assignment.retake_count == 1
    assert [issue["code"] for issue in first.ai_feedback["issues"]] == ["TOO_DARK"]

    second = _submit_and_validate(session, task=task, assignment=assignment, worker=users["worker"])
    assert second.ai_validation_status is ValidationStatus.APPROVED
    assert assignment.status is AssignmentStatus.APPROVED
    assert assignment.completed_at is not None
    assert task.status is TaskStatus.COMPLETED
    assert task.approved_worker_count == 1
    # 合格でワーカーの信頼度が加点される（docs/02-database.md 2.1）
    assert float(users["worker"].trust_score) == 94.0
    assert users["worker"].completed_task_count == 1
    # マスキングを通した画像が配信用バケットへ置かれる
    assert second.processed_image_url is not None
    assert second.masking_result["skipped"] is False
    # スタブモードでは座標問い合わせが空を返すため、加工領域は無い
    assert second.masking_result["regions"] == []


def test_retake_limit_fails_assignment_and_reopens_slot(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """3回不合格で failed になり、枠が他ワーカーへ再開放される（D-08）。"""
    settings = get_settings()
    # スタブは偶数回目を88点で返すため、閾値を上げて全提出を不合格にする
    monkeypatch.setattr(settings, "submission_score_threshold", 100)

    task = make_task(session, client=users["client"])
    assignment = make_assignment(session, task=task, worker=users["worker"])
    task.status = TaskStatus.IN_PROGRESS
    session.commit()

    for expected_retake in (1, 2):
        _submit_and_validate(session, task=task, assignment=assignment, worker=users["worker"])
        assert assignment.status is AssignmentStatus.ACCEPTED
        assert assignment.retake_count == expected_retake

    third = _submit_and_validate(session, task=task, assignment=assignment, worker=users["worker"])
    assert third.ai_validation_status is ValidationStatus.REJECTED
    assert assignment.status is AssignmentStatus.FAILED
    assert assignment.completed_at is not None
    assert assignment.retake_count == settings.max_retake_count
    # 失格で減点される
    assert float(users["worker"].trust_score) == 87.0
    # 枠が空いたので掲示板へ戻る
    assert task.status is TaskStatus.OPEN
    assert assignment_repo.count_active(session, task.id) == 0

    # 他のワーカーが受注できる
    detail = task_service.accept_task(session, worker=users["worker2"], task_id=task.id)
    assert detail.status is AssignmentStatus.ACCEPTED


def test_validation_error_does_not_consume_retake(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI呼び出しが失敗しても error になるだけで、再撮影回数は消費しない。"""
    task = make_task(session, client=users["client"])
    assignment = make_assignment(session, task=task, worker=users["worker"])

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("AI呼び出しの模擬失敗")

    monkeypatch.setattr(submission_pipeline.image_validation, "validate_image", boom)

    submission = _submit_and_validate(
        session, task=task, assignment=assignment, worker=users["worker"]
    )
    assert submission.ai_validation_status is ValidationStatus.ERROR
    assert assignment.retake_count == 0
    assert assignment.status is AssignmentStatus.ACCEPTED
    assert submission.ai_feedback["issues"][0]["code"] == "OTHER"


# ----------------------------------------------------------------------
# 期限超過
# ----------------------------------------------------------------------
def test_accept_after_deadline_is_rejected(session: Session, users: dict[str, User]) -> None:
    """期限を過ぎた依頼は受注できない（docs/03-api.md 3.5）。"""
    task = make_task(session, client=users["client"], deadline_offset_hours=-1)

    with pytest.raises(Conflict) as exc:
        task_service.accept_task(session, worker=users["worker"], task_id=task.id)
    assert exc.value.code == "INVALID_STATE"


def test_expired_task_is_not_reopened(session: Session, users: dict[str, User]) -> None:
    """期限切れの依頼は、受注者が0人になっても掲示板へ戻さない。"""
    task = make_task(session, client=users["client"], deadline_offset_hours=1)
    task.status = TaskStatus.IN_PROGRESS
    task.deadline_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()

    task_service.reopen_if_slot_available(session, task)
    assert task.status is TaskStatus.IN_PROGRESS


async def test_expired_task_is_hidden_from_nearby(session: Session, users: dict[str, User]) -> None:
    """期限切れの依頼は近傍検索に出てこない。"""
    make_task(session, client=users["client"], deadline_offset_hours=-1)
    found = await task_service.find_nearby(
        session,
        viewer=users["worker"],
        storage=get_storage(),
        lat=35.6595,
        lng=139.7005,
        radius_km=5,
        limit=50,
        sort="distance",
    )
    assert found == []


def test_stale_capture_is_rejected(session: Session, users: dict[str, User]) -> None:
    """撮り置き画像の投稿を防ぐ（capturedAt が古すぎる場合は 400）。"""
    from app.core.exceptions import ValidationError
    from app.services.submission_service import SubmissionInput, create_submission

    task = make_task(session, client=users["client"])
    assignment = make_assignment(session, task=task, worker=users["worker"])
    settings = get_settings()
    stale = datetime.now(UTC) - timedelta(seconds=settings.capture_freshness_seconds + 60)

    class _DummyUpload:
        content_type = "image/jpeg"

        async def read(self) -> bytes:  # pragma: no cover - 到達しない
            return b"\xff\xd8\xff\xd9"

    with pytest.raises(ValidationError) as exc:
        asyncio.run(
            create_submission(
                session,
                worker=users["worker"],
                data=SubmissionInput(
                    assignment_id=assignment.id,
                    captured_lat=task.location_lat,
                    captured_lng=task.location_lng,
                    captured_at=stale,
                ),
                image=_DummyUpload(),  # type: ignore[arg-type]
                storage=None,  # type: ignore[arg-type]
            )
        )
    assert exc.value.details["field"] == "capturedAt"
