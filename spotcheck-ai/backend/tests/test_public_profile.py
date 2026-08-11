"""公開プロフィールのテスト（docs/03-api.md 3.4.1）。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models import TaskStatus, User
from app.services import user_service
from tests.conftest import CLIENT_ID, WORKER_ID, auth_headers, make_task


def create_tasks(session: Session, client: User, statuses: list[str]) -> None:
    for status in statuses:
        make_task(session, client=client, status=status)


# ----------------------------------------------------------------------
# 公開範囲
# ----------------------------------------------------------------------
def test_response_never_contains_email_or_login_id(
    session: Session, users: dict[str, User]
) -> None:
    """非公開項目がレスポンスに現れないことを機械的に検証する。"""
    with TestClient(app) as client:
        response = client.get(f"/api/users/{CLIENT_ID}/public", headers=auth_headers(WORKER_ID))

    assert response.status_code == 200
    body = response.text
    assert users["client"].email not in body
    for forbidden in ("email", "login_id", "loginId", "password"):
        assert forbidden not in body


def test_rejected_and_screening_tasks_are_excluded(
    session: Session, users: dict[str, User]
) -> None:
    """却下・審査中・情報補足待ちの依頼は母数に含めない。"""
    create_tasks(
        session,
        users["client"],
        ["open", "completed", "rejected", "screening", "needs_info"],
    )

    profile = user_service.build_public_profile(session, CLIENT_ID)

    # open + completed の2件だけが母数
    assert profile.as_requester.published_task_count == 2
    assert profile.as_requester.completed_task_count == 1
    assert profile.as_requester.completion_rate == 0.5


def test_expired_and_cancelled_count_as_published(session: Session, users: dict[str, User]) -> None:
    """一度公開された依頼は、期限切れ・取消でも母数に含める。"""
    create_tasks(session, users["client"], ["expired", "cancelled", "completed"])

    profile = user_service.build_public_profile(session, CLIENT_ID)

    assert profile.as_requester.published_task_count == 3
    assert profile.as_requester.completed_task_count == 1


# ----------------------------------------------------------------------
# 完了率
# ----------------------------------------------------------------------
def test_completion_rate_is_null_without_published_tasks(
    session: Session, users: dict[str, User]
) -> None:
    profile = user_service.build_public_profile(session, CLIENT_ID)

    assert profile.as_requester.published_task_count == 0
    assert profile.as_requester.completion_rate is None


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["completed"], 1.0),
        (["completed", "open"], 0.5),
        (["completed", "completed", "open", "expired"], 0.5),
        (["open", "open"], 0.0),
    ],
)
def test_completion_rate(
    session: Session, users: dict[str, User], statuses: list[str], expected: float
) -> None:
    create_tasks(session, users["client"], statuses)
    profile = user_service.build_public_profile(session, CLIENT_ID)
    assert profile.as_requester.completion_rate == expected


# ----------------------------------------------------------------------
# 両面表示
# ----------------------------------------------------------------------
def test_worker_stats_keep_hundred_point_scale(session: Session, users: dict[str, User]) -> None:
    """信頼度は 0〜100 のまま返す（画面が TrustGauge で表示するため換算しない）。"""
    profile = user_service.build_public_profile(session, WORKER_ID)

    assert profile.as_worker.trust_score == 92.0
    assert profile.as_worker.approved_submission_count == 0


def test_both_sides_are_returned_even_when_empty(session: Session, users: dict[str, User]) -> None:
    """実績が0でも両方のセクションを返す（表示側で空状態を出す）。"""
    profile = user_service.build_public_profile(session, WORKER_ID)

    assert profile.as_requester.published_task_count == 0
    assert profile.as_worker is not None
    assert profile.display_name == "山田 太郎"
    assert profile.joined_at is not None


def test_requester_can_also_have_worker_stats(session: Session, users: dict[str, User]) -> None:
    """1アカウントが依頼者とワーカーの両面を持ちうる（role に依存しない）。"""
    create_tasks(session, users["client"], ["completed"])
    users["client"].trust_score = 60
    users["client"].completed_task_count = 3
    session.commit()

    profile = user_service.build_public_profile(session, CLIENT_ID)

    assert profile.as_requester.completed_task_count == 1
    assert profile.as_worker.trust_score == 60.0
    assert profile.as_worker.approved_submission_count == 3


# ----------------------------------------------------------------------
# 認可
# ----------------------------------------------------------------------
def test_unauthenticated_is_rejected(session: Session, users: dict[str, User]) -> None:
    with TestClient(app) as client:
        response = client.get(f"/api/users/{CLIENT_ID}/public")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_unknown_user_returns_404(session: Session, users: dict[str, User]) -> None:
    unknown = "99999999-9999-9999-9999-999999999999"
    with TestClient(app) as client:
        response = client.get(f"/api/users/{unknown}/public", headers=auth_headers(WORKER_ID))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


def test_worker_can_view_client_and_client_can_view_worker(
    session: Session, users: dict[str, User]
) -> None:
    """ロールの制約なく相互に閲覧できる。"""
    with TestClient(app) as client:
        as_worker = client.get(f"/api/users/{CLIENT_ID}/public", headers=auth_headers(WORKER_ID))
        as_client = client.get(f"/api/users/{WORKER_ID}/public", headers=auth_headers(CLIENT_ID))

    assert as_worker.status_code == 200
    assert as_client.status_code == 200


# ----------------------------------------------------------------------
# 画面⑤への導線（TaskDetail.requester）
# ----------------------------------------------------------------------
def test_task_detail_includes_requester_summary(session: Session, users: dict[str, User]) -> None:
    create_tasks(session, users["client"], ["completed"])
    task = make_task(session, client=users["client"])

    with TestClient(app) as client:
        response = client.get(f"/api/tasks/{task.id}", headers=auth_headers(WORKER_ID))

    assert response.status_code == 200
    owner = response.json()["owner"]
    assert owner["id"] == str(CLIENT_ID)
    assert owner["displayName"] == "デモ株式会社"
    # completed 1件 + いま作った open 1件 → 母数2・完了1
    assert owner["publishedTaskCount"] == 2
    assert owner["completionRate"] == 0.5
    # 依頼主の要約にも非公開項目は載せない
    assert "email" not in json.dumps(owner)


def test_task_detail_requester_is_present_for_client_too(
    session: Session, users: dict[str, User]
) -> None:
    """クライアント自身が見ても同じ形で返す（出し分けはしない）。"""
    task = make_task(session, client=users["client"])

    with TestClient(app) as client:
        response = client.get(f"/api/tasks/{task.id}", headers=auth_headers(CLIENT_ID))

    assert response.json()["owner"]["id"] == str(CLIENT_ID)


def test_requester_summary_excludes_unpublished_tasks(
    session: Session, users: dict[str, User]
) -> None:
    make_task(session, client=users["client"], status="rejected")
    task = make_task(session, client=users["client"], status="open")

    with TestClient(app) as client:
        response = client.get(f"/api/tasks/{task.id}", headers=auth_headers(WORKER_ID))

    assert response.json()["owner"]["publishedTaskCount"] == 1


def test_task_status_enum_covers_public_statuses() -> None:
    """PUBLIC_TASK_STATUSES に未公開のステータスが混ざっていないことを固定する。"""
    from app.models import PUBLIC_TASK_STATUSES

    assert set(PUBLIC_TASK_STATUSES) == {
        TaskStatus.OPEN,
        TaskStatus.IN_PROGRESS,
        TaskStatus.COMPLETED,
        TaskStatus.EXPIRED,
        TaskStatus.CANCELLED,
    }
