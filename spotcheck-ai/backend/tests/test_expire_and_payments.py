"""期限超過ジョブと決済スタブのテスト（docs/03-api.md 4節 / D-03）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.jobs import expire_tasks
from app.models import (
    AssignmentStatus,
    Payment,
    PaymentDirection,
    PaymentStatus,
    TaskStatus,
    User,
    ValidationStatus,
)
from app.services import task_service
from tests.conftest import make_assignment, make_task
from tests.test_submission_pipeline import submit_and_validate, vlm_output


def overdue(session: Session, task) -> None:
    task.deadline_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()


# ----------------------------------------------------------------------
# 期限超過
# ----------------------------------------------------------------------
def test_overdue_task_becomes_expired(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])
    overdue(session, task)

    summary = expire_tasks.expire_overdue_tasks(session)
    session.commit()

    assert summary.expired == 1
    assert summary.completed == 0
    assert task.status is TaskStatus.EXPIRED


def test_overdue_task_with_approved_submission_becomes_completed(
    session: Session, users: dict[str, User]
) -> None:
    """合格済み提出がある状態で期限が切れた場合は completed になる。"""
    task = make_task(session, client=users["client"])
    task.approved_worker_count = 1
    task.status = TaskStatus.IN_PROGRESS
    overdue(session, task)

    summary = expire_tasks.expire_overdue_tasks(session)
    session.commit()

    assert summary.completed == 1
    assert summary.expired == 0
    assert task.status is TaskStatus.COMPLETED


def test_unfinished_assignments_are_expired(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])
    assignment = make_assignment(session, task=task, worker=users["worker"])
    task.status = TaskStatus.IN_PROGRESS
    overdue(session, task)

    expire_tasks.expire_overdue_tasks(session)
    session.commit()

    assert assignment.status is AssignmentStatus.EXPIRED
    assert assignment.completed_at is not None
    assert task.status is TaskStatus.EXPIRED


def test_expired_task_disappears_from_worker_list(session: Session, users: dict[str, User]) -> None:
    """期限切れになったタスクはワーカー側の一覧から消える。"""
    task = make_task(session, client=users["client"])
    found = task_service.find_nearby(
        session,
        viewer_id=users["worker"].id,
        lat=task.location_lat,
        lng=task.location_lng,
        radius_km=5,
        limit=50,
        sort="distance",
    )
    assert [item.id for item in found] == [task.id]

    overdue(session, task)
    expire_tasks.expire_overdue_tasks(session)
    session.commit()

    assert (
        task_service.find_nearby(
            session,
            viewer_id=users["worker"].id,
            lat=task.location_lat,
            lng=task.location_lng,
            radius_km=5,
            limit=50,
            sort="distance",
        )
        == []
    )


def test_tasks_within_deadline_are_untouched(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])
    summary = expire_tasks.expire_overdue_tasks(session)
    assert summary.total == 0
    assert task.status is TaskStatus.OPEN


def test_completed_task_is_not_reprocessed(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])
    task.status = TaskStatus.COMPLETED
    overdue(session, task)

    summary = expire_tasks.expire_overdue_tasks(session)
    assert summary.total == 0
    assert task.status is TaskStatus.COMPLETED


def test_run_once_commits_in_its_own_session(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])
    overdue(session, task)

    summary = expire_tasks.run_once()

    assert summary.expired == 1
    session.expire_all()
    assert task.status is TaskStatus.EXPIRED


# ----------------------------------------------------------------------
# 決済スタブ
# ----------------------------------------------------------------------
def test_approval_records_charge_and_payout(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """検品合格で payments に charge / payout が1件ずつ記録される。"""
    submission = submit_and_validate(session, users, monkeypatch, vlm=vlm_output())
    assert submission.ai_validation_status is ValidationStatus.APPROVED

    payments = list(session.scalars(select(Payment).order_by(Payment.direction)))
    assert len(payments) == 2

    charge = next(p for p in payments if p.direction is PaymentDirection.CHARGE)
    payout = next(p for p in payments if p.direction is PaymentDirection.PAYOUT)

    assert charge.user_id == users["client"].id
    assert payout.user_id == users["worker"].id
    assert charge.amount == payout.amount == 2000
    assert charge.status is PaymentStatus.STUB_SUCCEEDED
    assert payout.status is PaymentStatus.STUB_SUCCEEDED
    assert charge.processed_at is not None
    assert charge.submission_id == submission.id


def test_rejection_records_no_payment(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    submission = submit_and_validate(
        session, users, monkeypatch, vlm=vlm_output(score=30, subject_present=False)
    )
    assert submission.ai_validation_status is ValidationStatus.REJECTED
    assert session.scalar(select(func.count()).select_from(Payment)) == 0


def test_payment_records_no_card_or_account_data(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """カード番号・口座番号を保存する列が存在しない（D-03）。"""
    submit_and_validate(session, users, monkeypatch, vlm=vlm_output())
    columns = set(Payment.__table__.columns.keys())
    assert not columns & {"card_number", "account_number", "token", "cvv"}
