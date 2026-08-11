"""プロフィール画像（アバター）の差し替えと配信URLの組み立て。

- 画像は正方形のJPEGへ揃えてから**加工済みバケット**へ保存する。
  原本バケットは提出画像の原本専用で、ここには置かない。
- DB（`users.avatar_url`）に持つのは保存キーだけで、URLは持たない。
- 配信URLは署名URLではなく `/api/users/{userId}/avatar?v=<版>` を返す。
  ログイン情報はブラウザの localStorage に残るため、有効期限付きURLを
  持たせると次回起動時に画像だけ表示できなくなるからである。
  `v` は画像内容のハッシュで、差し替え時にブラウザのキャッシュを外すために付ける。
"""

from __future__ import annotations

import hashlib
import uuid

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.storage import StorageBackend
from app.models import User
from app.services.thumbnail_service import to_square_jpeg
from app.services.uploads import read_and_validate_image

logger = get_logger(__name__)

#: 保存キーの接頭辞（加工済みバケット内）
AVATAR_PREFIX = "user-avatar"
#: 一覧・ヘッダーでの表示は最大でも 96px 程度のため、この大きさで十分。
AVATAR_SIZE = 256
#: 保存キーに埋める版（画像内容のハッシュ）の長さ
VERSION_LENGTH = 16


def _build_key(user_id: uuid.UUID, version: str) -> str:
    return f"{AVATAR_PREFIX}/{user_id}/{version}.jpg"


def _version_of(key: str) -> str:
    """保存キーから版（ファイル名部分）を取り出す。"""
    return key.rsplit("/", 1)[-1].removesuffix(".jpg")


def public_url(user: User) -> str | None:
    """アバターの配信URL。未設定なら None（画面側は頭文字の丸を出す）。"""
    if not user.avatar_url:
        return None
    return f"/api/users/{user.id}/avatar?v={_version_of(user.avatar_url)}"


async def replace(
    session: Session, *, user: User, image: UploadFile, storage: StorageBackend
) -> User:
    """アップロードされた画像でアバターを差し替える。

    保存に成功してから DB を更新する。古い画像は削除するが、削除に失敗しても
    差し替え自体は成功として扱う（残骸が残るだけで表示には影響しない）。
    """
    data, _ = await read_and_validate_image(image, field="image")
    square = to_square_jpeg(data, size=AVATAR_SIZE)
    version = hashlib.sha256(square).hexdigest()[:VERSION_LENGTH]
    key = _build_key(user.id, version)

    bucket = get_settings().storage_bucket_processed
    await storage.upload(bucket=bucket, key=key, data=square, content_type="image/jpeg")

    previous = user.avatar_url
    user.avatar_url = key
    session.commit()
    session.refresh(user)

    if previous and previous != key:
        await _delete_quietly(storage, bucket=bucket, key=previous)
    logger.info("アバターを更新しました", extra={"user_id": str(user.id)})
    return user


async def remove(session: Session, *, user: User, storage: StorageBackend) -> User:
    """アバターを削除して既定表示（頭文字の丸）へ戻す。"""
    previous = user.avatar_url
    if previous is None:
        return user

    user.avatar_url = None
    session.commit()
    session.refresh(user)

    await _delete_quietly(storage, bucket=get_settings().storage_bucket_processed, key=previous)
    logger.info("アバターを削除しました", extra={"user_id": str(user.id)})
    return user


async def load_image(user: User, storage: StorageBackend) -> bytes | None:
    """配信用に保存済みのアバター画像を読み出す。未設定なら None。"""
    if not user.avatar_url:
        return None
    return await storage.download(
        bucket=get_settings().storage_bucket_processed, key=user.avatar_url
    )


async def _delete_quietly(storage: StorageBackend, *, bucket: str, key: str) -> None:
    try:
        await storage.delete(bucket=bucket, key=key)
    except Exception:  # noqa: BLE001 - 残骸が残るだけなので処理は続行する
        logger.warning("古いアバター画像を削除できませんでした", extra={"key": key})
