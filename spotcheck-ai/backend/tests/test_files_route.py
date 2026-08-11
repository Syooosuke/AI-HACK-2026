"""ローカルストレージ配信エンドポイントのテスト（`GET /api/files/{bucket}/{key}`）。

原本バケットは絶対に配信しない。存在しないキーは 500 ではなく 404 を返す。
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.exceptions import StorageError, StorageObjectNotFound
from app.core.storage import SupabaseStorageBackend, get_storage
from app.main import app
from tests.conftest import store_raw_image, tiny_jpeg


def test_processed_image_is_served() -> None:
    settings = get_settings()
    key = "served/1.jpg"
    store_raw_image(key, bucket=settings.storage_bucket_processed)

    with TestClient(app) as client:
        response = client.get(f"/api/files/{settings.storage_bucket_processed}/{key}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == tiny_jpeg()


def test_raw_bucket_is_forbidden() -> None:
    """URLを推測されても原本は返さない。"""
    settings = get_settings()
    key = "secret/1.jpg"
    store_raw_image(key)  # 原本バケットに実在させる

    with TestClient(app) as client:
        response = client.get(f"/api/files/{settings.storage_bucket_raw}/{key}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    # 中身が漏れていないこと
    assert tiny_jpeg() not in response.content


def test_missing_key_returns_404() -> None:
    """存在しないキーは 404。保存や通信の失敗（500）と区別する。"""
    settings = get_settings()

    with TestClient(app) as client:
        response = client.get(f"/api/files/{settings.storage_bucket_processed}/missing.jpg")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_local_backend_raises_object_not_found() -> None:
    settings = get_settings()
    with pytest.raises(StorageObjectNotFound) as exc:
        await get_storage().download(
            bucket=settings.storage_bucket_processed, key="nope/nothing.jpg"
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "NOT_FOUND"


# ----------------------------------------------------------------------
# Supabase バックエンドの不在判定
# ----------------------------------------------------------------------
def supabase_backend(handler) -> SupabaseStorageBackend:
    settings = Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_secret_key="sb_secret_x",
    )
    return SupabaseStorageBackend(settings, transport=httpx.MockTransport(handler))


async def test_supabase_400_with_no_such_key_is_not_found() -> None:
    """Supabase は不在オブジェクトを HTTP 400 + NoSuchKey で返す（実測）。"""
    body = {
        "statusCode": "404",
        "error": "not_found",
        "message": "Object not found",
        "code": "NoSuchKey",
    }
    backend = supabase_backend(lambda _request: httpx.Response(400, json=body))

    with pytest.raises(StorageObjectNotFound):
        await backend.download(bucket="submissions-processed", key="missing.jpg")
    await backend.close()


async def test_supabase_404_is_not_found() -> None:
    backend = supabase_backend(lambda _request: httpx.Response(404, text="not found"))
    with pytest.raises(StorageObjectNotFound):
        await backend.download(bucket="submissions-processed", key="missing.jpg")
    await backend.close()


async def test_supabase_other_400_stays_storage_error() -> None:
    """不在以外の 400 は 500（STORAGE_ERROR）のまま扱う。"""
    backend = supabase_backend(
        lambda _request: httpx.Response(400, json={"error": "invalid_request"})
    )
    with pytest.raises(StorageError) as exc:
        await backend.download(bucket="submissions-processed", key="x.jpg")
    assert not isinstance(exc.value, StorageObjectNotFound)
    assert exc.value.status_code == 500
    await backend.close()


async def test_supabase_success_returns_bytes() -> None:
    backend = supabase_backend(lambda _request: httpx.Response(200, content=tiny_jpeg()))
    assert await backend.download(bucket="submissions-processed", key="ok.jpg") == tiny_jpeg()
    await backend.close()
