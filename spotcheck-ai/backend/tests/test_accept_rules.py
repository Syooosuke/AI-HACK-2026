"""受注の可否に関する規則。

- 一度辞退したワーカーが、同じ依頼を受け直せること
- 依頼者が指定した「最低平均評価」で受注を絞れること
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models import (
    AssignmentStatus,
    Submission,
    TaskAssignment,
    User,
    ValidationStatus,
    WorkerReview,
)
from tests.conftest import auth_headers, make_task


def _accept(api: TestClient, task_id: object, user: User):
    return api.post(f"/api/tasks/{task_id}/accept", headers=auth_headers(user))


def _withdraw(api: TestClient, task_id: object, user: User):
    return api.post(f"/api/tasks/{task_id}/withdraw", headers=auth_headers(user))


# ----------------------------------------------------------------------
# 辞退した後の受け直し
# ----------------------------------------------------------------------
def test_worker_can_accept_again_after_withdrawing(
    session: Session, users: dict[str, User]
) -> None:
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        assert _accept(api, task.id, users["worker"]).status_code == 201
        assert _withdraw(api, task.id, users["worker"]).status_code == 200
        again = _accept(api, task.id, users["worker"])

    assert again.status_code == 201
    assert again.json()["assignment"]["status"] == "accepted"

    # 一意制約があるため行は増えず、同じ受注が再開される
    rows = session.query(TaskAssignment).filter_by(task_id=task.id).all()
    assert len(rows) == 1
    assert rows[0].status is AssignmentStatus.ACCEPTED
    assert rows[0].completed_at is None


def test_reaccepting_keeps_retake_count(session: Session, users: dict[str, User]) -> None:
    """辞退→受け直しで再撮影の回数はやり直せない（D-08の上限を空洞化させないため）。"""
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        _accept(api, task.id, users["worker"])
        assignment = (
            session.query(TaskAssignment)
            .filter_by(task_id=task.id, worker_id=users["worker"].id)
            .one()
        )
        assignment.retake_count = 1
        assignment.status = AssignmentStatus.CANCELLED
        assignment.completed_at = datetime.now(UTC)
        session.commit()

        response = _accept(api, task.id, users["worker"])

    assert response.status_code == 201
    assert response.json()["assignment"]["retakeCount"] == 1
    assert response.json()["assignment"]["remainingRetakes"] == 1


def test_failed_worker_cannot_accept_again(session: Session, users: dict[str, User]) -> None:
    """再撮影の上限を超えて失格になったワーカーは受け直せない。"""
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        _accept(api, task.id, users["worker"])
        assignment = (
            session.query(TaskAssignment)
            .filter_by(task_id=task.id, worker_id=users["worker"].id)
            .one()
        )
        assignment.status = AssignmentStatus.FAILED
        session.commit()

        response = _accept(api, task.id, users["worker"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_ACCEPTED"


# ----------------------------------------------------------------------
# 最低平均評価
# ----------------------------------------------------------------------
def _give_rating(session: Session, *, worker: User, reviewer: User, rating: int) -> None:
    """評価を1件作る。評価は提出に紐づくため、提出も併せて用意する。"""
    task = make_task(session, client=reviewer)
    assignment = TaskAssignment(task_id=task.id, worker_id=worker.id)
    session.add(assignment)
    session.flush()
    submission = Submission(
        task_id=task.id,
        assignment_id=assignment.id,
        worker_id=worker.id,
        attempt_no=1,
        raw_image_url="raw/x.jpg",
        captured_at=datetime.now(UTC),
        captured_lat=35.6595,
        captured_lng=139.7005,
        ai_validation_status=ValidationStatus.APPROVED,
    )
    session.add(submission)
    session.flush()
    session.add(
        WorkerReview(
            submission_id=submission.id,
            task_id=task.id,
            reviewer_id=reviewer.id,
            worker_id=worker.id,
            rating=rating,
            tags=[],
        )
    )
    session.commit()


def test_worker_below_required_rating_is_rejected(session: Session, users: dict[str, User]) -> None:
    _give_rating(session, worker=users["worker"], reviewer=users["worker2"], rating=2)

    task = make_task(session, client=users["client"])
    task.min_worker_rating = 4.0
    session.commit()

    with TestClient(app) as api:
        response = _accept(api, task.id, users["worker"])

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "RATING_REQUIREMENT_NOT_MET"


def test_worker_meeting_required_rating_can_accept(
    session: Session, users: dict[str, User]
) -> None:
    _give_rating(session, worker=users["worker"], reviewer=users["worker2"], rating=5)

    task = make_task(session, client=users["client"])
    task.min_worker_rating = 4.0
    session.commit()

    with TestClient(app) as api:
        response = _accept(api, task.id, users["worker"])

    assert response.status_code == 201


def test_worker_without_reviews_is_not_filtered_out(
    session: Session, users: dict[str, User]
) -> None:
    """評価が1件も無い新規ワーカーは足切りしない。

    足切りすると評価を得る機会が無く、条件付きの依頼が誰にも受けられなくなる。
    """
    task = make_task(session, client=users["client"])
    task.min_worker_rating = 5.0
    session.commit()

    with TestClient(app) as api:
        response = _accept(api, task.id, users["worker"])

    assert response.status_code == 201


def test_min_worker_rating_is_returned_in_task_detail(
    session: Session, users: dict[str, User]
) -> None:
    task = make_task(session, client=users["client"])
    task.min_worker_rating = 3.5
    session.commit()

    with TestClient(app) as api:
        response = api.get(f"/api/tasks/{task.id}", headers=auth_headers(users["worker"]))

    assert response.status_code == 200
    assert response.json()["minWorkerRating"] == 3.5
