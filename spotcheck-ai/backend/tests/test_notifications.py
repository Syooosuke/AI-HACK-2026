"""お知らせ（アプリ内通知）のテスト。

通知は既存のステータス遷移に連動して作られる。**誰に届くか**と
**業務処理との整合**（受注が成立したら必ず通知が残る等）を固定する。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Notification, NotificationType, TaskStatus, User
from app.repositories import notification_repo
from tests.conftest import auth_headers, make_task


def make_notification(
    session: Session,
    *,
    user: User,
    title: str = "テスト通知",
    type: NotificationType = NotificationType.TASK_ACCEPTED,
) -> Notification:
    notification = notification_repo.create(
        session, user_id=user.id, type=type, title=title, body="本文"
    )
    session.commit()
    return notification


# ----------------------------------------------------------------------
# 一覧・未読件数
# ----------------------------------------------------------------------
def test_list_is_empty_at_first(users: dict[str, User]) -> None:
    with TestClient(app) as api:
        body = api.get("/api/notifications", headers=auth_headers(users["worker"])).json()

    assert body == {"notifications": []}


def test_list_returns_only_own_notifications_newest_first(
    session: Session, users: dict[str, User]
) -> None:
    make_notification(session, user=users["worker"], title="古い通知")
    make_notification(session, user=users["worker"], title="新しい通知")
    make_notification(session, user=users["worker2"], title="他人の通知")

    with TestClient(app) as api:
        body = api.get("/api/notifications", headers=auth_headers(users["worker"])).json()

    assert [item["title"] for item in body["notifications"]] == ["新しい通知", "古い通知"]


def test_unread_count(session: Session, users: dict[str, User]) -> None:
    make_notification(session, user=users["worker"])
    make_notification(session, user=users["worker"])
    make_notification(session, user=users["worker2"])

    with TestClient(app) as api:
        mine = api.get(
            "/api/notifications/unread-count", headers=auth_headers(users["worker"])
        ).json()
        other = api.get(
            "/api/notifications/unread-count", headers=auth_headers(users["worker2"])
        ).json()

    assert mine == {"count": 2}
    assert other == {"count": 1}


def test_notifications_require_login() -> None:
    with TestClient(app) as api:
        assert api.get("/api/notifications").status_code == 401
        assert api.get("/api/notifications/unread-count").status_code == 401


# ----------------------------------------------------------------------
# 既読
# ----------------------------------------------------------------------
def test_mark_read_reduces_unread_count(session: Session, users: dict[str, User]) -> None:
    first = make_notification(session, user=users["worker"])
    make_notification(session, user=users["worker"])
    headers = auth_headers(users["worker"])

    with TestClient(app) as api:
        response = api.post(f"/api/notifications/{first.id}/read", headers=headers)
        count = api.get("/api/notifications/unread-count", headers=headers).json()

    assert response.status_code == 204
    assert count == {"count": 1}


def test_mark_read_is_idempotent(session: Session, users: dict[str, User]) -> None:
    notification = make_notification(session, user=users["worker"])
    headers = auth_headers(users["worker"])

    with TestClient(app) as api:
        api.post(f"/api/notifications/{notification.id}/read", headers=headers)
        second = api.post(f"/api/notifications/{notification.id}/read", headers=headers)
        count = api.get("/api/notifications/unread-count", headers=headers).json()

    assert second.status_code == 204
    assert count == {"count": 0}


def test_cannot_read_others_notification(session: Session, users: dict[str, User]) -> None:
    """他人の通知は既読にできない（存在を教えないため404）。"""
    notification = make_notification(session, user=users["worker"])

    with TestClient(app) as api:
        response = api.post(
            f"/api/notifications/{notification.id}/read", headers=auth_headers(users["worker2"])
        )

    assert response.status_code == 404
    session.expire_all()
    assert notification_repo.count_unread(session, users["worker"].id) == 1


def test_mark_all_read_only_affects_own(session: Session, users: dict[str, User]) -> None:
    make_notification(session, user=users["worker"])
    make_notification(session, user=users["worker"])
    make_notification(session, user=users["worker2"])

    with TestClient(app) as api:
        response = api.post("/api/notifications/read-all", headers=auth_headers(users["worker"]))
        mine = api.get(
            "/api/notifications/unread-count", headers=auth_headers(users["worker"])
        ).json()
        other = api.get(
            "/api/notifications/unread-count", headers=auth_headers(users["worker2"])
        ).json()

    assert response.status_code == 204
    assert mine == {"count": 0}
    # 他人の未読は残る
    assert other == {"count": 1}


# ----------------------------------------------------------------------
# 業務処理との連動
# ----------------------------------------------------------------------
def test_accepting_task_notifies_owner_only(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        accepted = api.post(f"/api/tasks/{task.id}/accept", headers=auth_headers(users["worker"]))
        owner = api.get("/api/notifications", headers=auth_headers(users["client"])).json()
        worker = api.get("/api/notifications", headers=auth_headers(users["worker"])).json()

    assert accepted.status_code == 201
    assert len(owner["notifications"]) == 1
    assert owner["notifications"][0]["type"] == "task_accepted"
    assert owner["notifications"][0]["taskId"] == str(task.id)
    # 受注した本人には出さない
    assert worker["notifications"] == []


def test_notification_is_committed_with_accept(session: Session, users: dict[str, User]) -> None:
    """受注が成立したら、通知も必ず残っている（同一トランザクションで確定する）。"""
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        api.post(f"/api/tasks/{task.id}/accept", headers=auth_headers(users["worker"]))

    session.expire_all()
    notification = session.scalars(
        select(Notification).where(Notification.user_id == users["client"].id)
    ).one()
    assert notification.type is NotificationType.TASK_ACCEPTED
    assert notification.read_at is None


def test_expired_task_notifies_owner(session: Session, users: dict[str, User]) -> None:
    """期限切れのクローズで依頼主へ通知が届く（jobs/expire_tasks 経由）。"""
    from app.jobs import expire_tasks

    task = make_task(session, client=users["client"], deadline_offset_hours=-1)

    expire_tasks.expire_overdue_tasks(session)
    session.commit()
    session.refresh(task)

    assert task.status is TaskStatus.EXPIRED
    notifications = session.scalars(
        select(Notification).where(Notification.user_id == users["client"].id)
    ).all()
    assert [n.type for n in notifications] == [NotificationType.TASK_EXPIRED]
