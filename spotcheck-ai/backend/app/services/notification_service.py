"""お知らせ（画面下部タブ）。

依頼審査・受注・検品結果・依頼完了/期限切れなど、既存のステータス遷移に連動して
`notify()` を呼び出すことで通知を作成する。呼び出し側の`session`をそのまま使い、
コミットは呼び出し元（APIの`get_db`依存 / `expire_tasks.run_once`）に任せる。
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.models import Notification, NotificationType, User
from app.repositories import notification_repo
from app.schemas.notification import NotificationItem, NotificationListResponse, UnreadCountResponse


def notify(
    session: Session,
    *,
    user_id: uuid.UUID,
    type: NotificationType,
    title: str,
    body: str | None = None,
    task_id: uuid.UUID | None = None,
    submission_id: uuid.UUID | None = None,
) -> Notification:
    return notification_repo.create(
        session,
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        task_id=task_id,
        submission_id=submission_id,
    )


def list_notifications(session: Session, user: User) -> NotificationListResponse:
    notifications = notification_repo.list_for_user(session, user.id)
    return NotificationListResponse(
        notifications=[NotificationItem.model_validate(n) for n in notifications]
    )


def unread_count(session: Session, user: User) -> UnreadCountResponse:
    return UnreadCountResponse(count=notification_repo.count_unread(session, user.id))


def mark_read(session: Session, *, user: User, notification_id: uuid.UUID) -> None:
    found = notification_repo.mark_read(session, user_id=user.id, notification_id=notification_id)
    if not found:
        raise NotFound("指定されたお知らせが見つかりません。", code="NOTIFICATION_NOT_FOUND")


def mark_all_read(session: Session, user: User) -> None:
    notification_repo.mark_all_read(session, user.id)
