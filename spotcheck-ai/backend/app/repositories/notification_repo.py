"""notifications テーブルへのアクセス。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Notification, NotificationType


def create(
    session: Session,
    *,
    user_id: uuid.UUID,
    type: NotificationType,
    title: str,
    body: str | None = None,
    task_id: uuid.UUID | None = None,
    submission_id: uuid.UUID | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        task_id=task_id,
        submission_id=submission_id,
    )
    session.add(notification)
    session.flush()
    return notification


def list_for_user(session: Session, user_id: uuid.UUID, *, limit: int = 50) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def count_unread(session: Session, user_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return session.scalar(stmt) or 0


def mark_read(session: Session, *, user_id: uuid.UUID, notification_id: uuid.UUID) -> bool:
    """既読にする。対象が無ければ False（他人の通知IDを指定した場合も含む）。

    **すでに既読でも True を返す（冪等）。** 未読の行だけを対象にすると、
    同じ通知を2回タップしたときに「見つからない」と誤判定してしまう。
    """
    stmt = (
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            # 既読の時刻は最初に読んだ時点を保つ（上書きしない）
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    if (session.execute(stmt).rowcount or 0) > 0:
        return True

    # 更新対象が無かった場合、「既読済み」と「他人の通知・存在しない」を区別する
    exists = session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user_id)
    )
    return bool(exists)


def mark_all_read(session: Session, user_id: uuid.UUID) -> int:
    stmt = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    return session.execute(stmt).rowcount or 0
