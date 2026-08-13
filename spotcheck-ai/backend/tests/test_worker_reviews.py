"""依頼者によるワーカー評価のAPIテスト。"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models import Submission, User, ValidationStatus
from tests.conftest import auth_headers, make_assignment, make_task


def make_submission(
    session: Session, users: dict[str, User], *, approved: bool = True
) -> Submission:
    task = make_task(session, client=users["client"], status="completed" if approved else "open")
    assignment = make_assignment(session, task=task, worker=users["worker"])
    submission = Submission(
        assignment_id=assignment.id,
        task_id=task.id,
        worker_id=users["worker"].id,
        attempt_no=1,
        raw_image_url="test/raw.jpg",
        captured_lat=task.location_lat,
        captured_lng=task.location_lng,
        captured_at=datetime.now(UTC),
        ai_validation_status=(ValidationStatus.APPROVED if approved else ValidationStatus.PENDING),
    )
    session.add(submission)
    session.commit()
    return submission


def test_requester_can_review_approved_submission(session: Session, users: dict[str, User]) -> None:
    submission = make_submission(session, users)
    with TestClient(app) as client:
        response = client.post(
            f"/api/submissions/{submission.id}/review",
            headers=auth_headers(users["client"]),
            json={
                "rating": 5,
                "tags": ["as_requested", "clear_photo"],
                "comment": "依頼どおりの分かりやすい写真でした。",
            },
        )
    assert response.status_code == 201
    assert response.json()["rating"] == 5
    assert response.json()["workerId"] == str(users["worker"].id)


def test_submission_can_only_be_reviewed_once(session: Session, users: dict[str, User]) -> None:
    submission = make_submission(session, users)
    with TestClient(app) as client:
        first = client.post(
            f"/api/submissions/{submission.id}/review",
            headers=auth_headers(users["client"]),
            json={"rating": 4},
        )
        second = client.post(
            f"/api/submissions/{submission.id}/review",
            headers=auth_headers(users["client"]),
            json={"rating": 5},
        )
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "REVIEW_ALREADY_EXISTS"


def test_only_requester_can_review(session: Session, users: dict[str, User]) -> None:
    submission = make_submission(session, users)
    with TestClient(app) as client:
        response = client.post(
            f"/api/submissions/{submission.id}/review",
            headers=auth_headers(users["worker2"]),
            json={"rating": 5},
        )
    assert response.status_code == 403


def test_pending_submission_cannot_be_reviewed(session: Session, users: dict[str, User]) -> None:
    submission = make_submission(session, users, approved=False)
    with TestClient(app) as client:
        response = client.post(
            f"/api/submissions/{submission.id}/review",
            headers=auth_headers(users["client"]),
            json={"rating": 5},
        )
    assert response.status_code == 409


def test_review_stats_are_shown_on_public_profile(session: Session, users: dict[str, User]) -> None:
    first = make_submission(session, users)
    second_task = make_task(session, client=users["client"], status="completed")
    second_assignment = make_assignment(session, task=second_task, worker=users["worker"])
    second = Submission(
        assignment_id=second_assignment.id,
        task_id=second_task.id,
        worker_id=users["worker"].id,
        attempt_no=1,
        raw_image_url="test/raw-2.jpg",
        captured_lat=second_task.location_lat,
        captured_lng=second_task.location_lng,
        captured_at=datetime.now(UTC),
        ai_validation_status=ValidationStatus.APPROVED,
    )
    session.add(second)
    session.commit()

    with TestClient(app) as client:
        for submission, rating in ((first, 4), (second, 5)):
            client.post(
                f"/api/submissions/{submission.id}/review",
                headers=auth_headers(users["client"]),
                json={"rating": rating},
            )
        profile = client.get(
            f"/api/users/{users['worker'].id}/public",
            headers=auth_headers(users["client"]),
        )

    assert profile.status_code == 200
    assert profile.json()["asWorker"]["averageRating"] == 4.5
    assert profile.json()["asWorker"]["reviewCount"] == 2


def test_worker_can_list_received_reviews_without_reviewer_identity(
    session: Session, users: dict[str, User]
) -> None:
    submission = make_submission(session, users)
    with TestClient(app) as client:
        created = client.post(
            f"/api/submissions/{submission.id}/review",
            headers=auth_headers(users["client"]),
            json={
                "rating": 5,
                "tags": ["as_requested"],
                "comment": "丁寧な写真でした。",
            },
        )
        response = client.get(
            "/api/users/me/reviews",
            headers=auth_headers(users["worker"]),
        )

    assert created.status_code == 201
    assert response.status_code == 200
    body = response.json()
    assert body["averageRating"] == 5.0
    assert body["reviewCount"] == 1
    assert body["reviews"][0]["taskTitle"] == "駅前の再開発工事の進捗確認"
    assert body["reviews"][0]["comment"] == "丁寧な写真でした。"
    serialized = response.text
    assert "reviewer" not in serialized
    assert users["client"].display_name not in serialized


def test_worker_sees_review_in_submission_status(session: Session, users: dict[str, User]) -> None:
    submission = make_submission(session, users)
    with TestClient(app) as client:
        client.post(
            f"/api/submissions/{submission.id}/review",
            headers=auth_headers(users["client"]),
            json={
                "rating": 4,
                "tags": ["clear_photo", "accurate_location"],
                "comment": "現地の様子が分かりやすかったです。",
            },
        )
        response = client.get(
            f"/api/submissions/{submission.id}",
            headers=auth_headers(users["worker"]),
        )

    assert response.status_code == 200
    review = response.json()["workerReview"]
    assert review["rating"] == 4
    assert review["tags"] == ["clear_photo", "accurate_location"]
    assert review["comment"] == "現地の様子が分かりやすかったです。"


def test_received_review_list_only_contains_own_reviews(
    session: Session, users: dict[str, User]
) -> None:
    submission = make_submission(session, users)
    with TestClient(app) as client:
        client.post(
            f"/api/submissions/{submission.id}/review",
            headers=auth_headers(users["client"]),
            json={"rating": 4},
        )
        other_worker = client.get(
            "/api/users/me/reviews",
            headers=auth_headers(users["worker2"]),
        )

    assert other_worker.status_code == 200
    assert other_worker.json() == {"reviews": [], "averageRating": None, "reviewCount": 0}
