"""お知らせ（画面下部タブ）のエンドポイント。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.notification import NotificationListResponse, UnreadCountResponse
from app.services import notification_service

router = APIRouter(prefix="/api", tags=["notifications"])


@router.get("/notifications", response_model=NotificationListResponse)
def list_notifications(session: DbSession, user: CurrentUser) -> NotificationListResponse:
    return notification_service.list_notifications(session, user)


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
def get_unread_count(session: DbSession, user: CurrentUser) -> UnreadCountResponse:
    return notification_service.unread_count(session, user)


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_notification_read(
    session: DbSession, user: CurrentUser, notification_id: uuid.UUID
) -> None:
    notification_service.mark_read(session, user=user, notification_id=notification_id)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_notifications_read(session: DbSession, user: CurrentUser) -> None:
    notification_service.mark_all_read(session, user)
