"""画像ストレージ。

Supabase Storage を本番の保存先とし、未設定時はローカルファイル保存へフォールバックする
（docs/01-architecture.md 4節）。呼び出し側は `StorageBackend` のインターフェースのみに依存し、
実装の差を意識しない。

バケットは2つに分離する。**どちらも非公開**とし、配信は署名URLで行う。
  - STORAGE_BUCKET_RAW       … 原本。APIレスポンスに含めてはならない
  - STORAGE_BUCKET_PROCESSED … マスキング済み。署名URLでクライアントへ配信する
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import StorageError, StorageObjectNotFound
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_SIGNED_URL_TTL_SECONDS = 3600  # docs/03-api.md 1.4: 有効期限1時間


def _is_object_not_found(response: httpx.Response) -> bool:
    """Supabase Storage の「オブジェクトが無い」応答を判定する。

    実測では **HTTP 400** に `{"statusCode":"404","error":"not_found","code":"NoSuchKey"}`
    を載せて返してくるため、ステータスコードだけでは区別できない。
    """
    if response.status_code == 404:
        return True
    if response.status_code != 400:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    if not isinstance(body, dict):
        return False
    return (
        str(body.get("statusCode")) == "404"
        or body.get("error") == "not_found"
        or body.get("code") == "NoSuchKey"
    )


class StorageBackend(ABC):
    """画像の保存と署名URL発行の窓口。"""

    name: str

    @abstractmethod
    async def ensure_buckets(self) -> dict[str, str]:
        """必要なバケットを用意する。バケット名 -> 結果（created / exists / skipped）を返す。"""

    @abstractmethod
    async def upload(self, *, bucket: str, key: str, data: bytes, content_type: str) -> str:
        """アップロードし、保存キー（バケット内パス）を返す。"""

    @abstractmethod
    async def download(self, *, bucket: str, key: str) -> bytes:
        """保存済みオブジェクトを取得する（検品・マスキング処理で使う）。"""

    @abstractmethod
    async def create_signed_url(
        self, *, bucket: str, key: str, expires_in: int = DEFAULT_SIGNED_URL_TTL_SECONDS
    ) -> str:
        """期限付きの配信URLを発行する。"""

    async def close(self) -> None:
        """保持しているリソースを解放する。"""


class SupabaseStorageBackend(StorageBackend):
    """Supabase Storage REST API（`/storage/v1`）を直接呼ぶ実装。"""

    name = "supabase"

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._base_url = f"{settings.supabase_url.rstrip('/')}/storage/v1"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {settings.supabase_key}",
                "apikey": settings.supabase_key,
            },
            timeout=30.0,
            transport=transport,
        )

    async def ensure_buckets(self) -> dict[str, str]:
        results: dict[str, str] = {}
        for bucket in (self._settings.storage_bucket_raw, self._settings.storage_bucket_processed):
            results[bucket] = await self._ensure_bucket(bucket)
        return results

    async def _ensure_bucket(self, bucket: str) -> str:
        payload = {
            "id": bucket,
            "name": bucket,
            # 原本・加工後ともに非公開。配信は署名URLのみ。
            "public": False,
            "allowed_mime_types": self._settings.allowed_image_type_list,
            "file_size_limit": self._settings.max_upload_size_bytes,
        }
        response = await self._client.post("/bucket", json=payload)
        if response.status_code < 300:
            logger.info("Storageバケットを作成しました", extra={"bucket": bucket})
            return "created"
        # 既存の場合は 400/409 が返る（メッセージで判別する）
        body = response.text
        if response.status_code in (400, 409) and "exist" in body.lower():
            return "exists"
        raise StorageError(
            f"バケット '{bucket}' の作成に失敗しました（HTTP {response.status_code}）。",
            details={"body": body[:500]},
        )

    async def upload(self, *, bucket: str, key: str, data: bytes, content_type: str) -> str:
        response = await self._client.post(
            f"/object/{bucket}/{key}",
            content=data,
            headers={"content-type": content_type, "x-upsert": "true"},
        )
        if response.status_code >= 300:
            raise StorageError(
                "画像の保存に失敗しました。",
                details={"status": response.status_code, "body": response.text[:500]},
            )
        return key

    async def download(self, *, bucket: str, key: str) -> bytes:
        response = await self._client.get(f"/object/{bucket}/{key}")
        if response.status_code >= 300:
            if _is_object_not_found(response):
                raise StorageObjectNotFound(details={"bucket": bucket, "key": key})
            raise StorageError(
                "画像の取得に失敗しました。",
                details={"status": response.status_code, "body": response.text[:500]},
            )
        return response.content

    async def create_signed_url(
        self, *, bucket: str, key: str, expires_in: int = DEFAULT_SIGNED_URL_TTL_SECONDS
    ) -> str:
        response = await self._client.post(
            f"/object/sign/{bucket}/{key}", json={"expiresIn": expires_in}
        )
        if response.status_code >= 300:
            raise StorageError(
                "画像URLの発行に失敗しました。",
                details={"status": response.status_code, "body": response.text[:500]},
            )
        signed_path = response.json().get("signedURL", "")
        return f"{self._base_url}{signed_path}" if signed_path.startswith("/") else signed_path

    async def close(self) -> None:
        await self._client.aclose()


class LocalStorageBackend(StorageBackend):
    """Supabase未設定時のフォールバック。ローカルディレクトリへ保存する。"""

    name = "local"

    def __init__(self, settings: Settings) -> None:
        self._root = Path(settings.local_storage_dir).resolve()
        self._settings = settings

    def _path(self, bucket: str, key: str) -> Path:
        # `..` を含むキーでルート外へ書き出されるのを防ぐ
        target = (self._root / bucket / key).resolve()
        if not target.is_relative_to(self._root):
            raise StorageError("不正な保存先が指定されました。")
        return target

    async def ensure_buckets(self) -> dict[str, str]:
        results: dict[str, str] = {}
        for bucket in (self._settings.storage_bucket_raw, self._settings.storage_bucket_processed):
            directory = self._root / bucket
            existed = directory.exists()
            directory.mkdir(parents=True, exist_ok=True)
            results[bucket] = "exists" if existed else "created"
        return results

    async def upload(self, *, bucket: str, key: str, data: bytes, content_type: str) -> str:
        path = self._path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def download(self, *, bucket: str, key: str) -> bytes:
        path = self._path(bucket, key)
        if not path.exists():
            raise StorageObjectNotFound(details={"bucket": bucket, "key": key})
        return path.read_bytes()

    async def create_signed_url(
        self, *, bucket: str, key: str, expires_in: int = DEFAULT_SIGNED_URL_TTL_SECONDS
    ) -> str:
        # 配信エンドポイント側でも processed バケット以外は拒否する。
        return f"/api/files/{bucket}/{key}"


@lru_cache
def get_storage() -> StorageBackend:
    settings = get_settings()
    if settings.effective_storage_backend == "supabase":
        return SupabaseStorageBackend(settings)
    return LocalStorageBackend(settings)
