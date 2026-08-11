"""ユーザープロフィール（アバター画像・公開プロフィール）のエンドポイント。

`GET /api/users/{userId}/avatar` は **認証不要**。`<img>` タグから読むため
Authorization ヘッダーを付けられず、また他ユーザーのアイコンも表示するためである。
返すのは本人がアップロードしたプロフィール画像だけで、提出画像の原本は一切扱わない。
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFound
from app.core.storage import get_storage
from app.repositories import user_repo
from app.schemas.auth import MeResponse
from app.schemas.user import PublicProfile
from app.services import auth_service, avatar_service, user_service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("/me/avatar", response_model=MeResponse)
async def upload_my_avatar(
    session: DbSession,
    user: CurrentUser,
    image: Annotated[UploadFile, File()],
) -> MeResponse:
    """自分のアバターを差し替える。更新後のユーザー情報を返す。"""
    updated = await avatar_service.replace(session, user=user, image=image, storage=get_storage())
    return MeResponse(user=auth_service.to_auth_user(updated))


@router.delete("/me/avatar", response_model=MeResponse)
async def delete_my_avatar(session: DbSession, user: CurrentUser) -> MeResponse:
    """自分のアバターを削除して既定表示へ戻す。"""
    updated = await avatar_service.remove(session, user=user, storage=get_storage())
    return MeResponse(user=auth_service.to_auth_user(updated))


@router.get("/{user_id}/avatar", response_class=Response)
async def get_avatar(session: DbSession, user_id: uuid.UUID) -> Response:
    """アバター画像を配信する（認証不要）。未設定・不在ユーザーはどちらも 404。"""
    user = user_repo.get(session, user_id)
    payload = await avatar_service.load_image(user, get_storage()) if user else None
    if payload is None:
        raise NotFound("アバター画像が設定されていません。")

    return Response(
        content=payload,
        media_type="image/jpeg",
        # URLに版（画像のハッシュ）が入るため、長めにキャッシュしてよい
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{user_id}/public", response_model=PublicProfile)
def get_public_profile(
    session: DbSession, viewer: CurrentUser, user_id: uuid.UUID
) -> PublicProfile:
    """閲覧専用の公開プロフィール（docs/03-api.md 3.4.1）。

    ロールによる出し分けはせず、ログインしていれば誰でも誰のプロフィールも見られる。
    公開してよい項目の判断は `app/services/user_service.py` に集約している。
    `viewer` は認証を要求するためだけに受け取る。
    """
    return user_service.build_public_profile(session, user_id)
