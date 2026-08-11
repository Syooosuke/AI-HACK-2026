"""Google Street View Static API から現地画像を取得する。

サーバー側の専用キー（`GOOGLE_MAPS_SERVER_API_KEY`）を使う。
フロント用のキーはブラウザに露出させる前提でリファラー制限をかけるため、
サーバーからは使えないので分けている。

キー未設定・API未有効・パノラマが存在しない地点では `None` を返す。
呼び出し側はプレースホルダへフォールバックする。
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"
REQUEST_TIMEOUT_SECONDS = 15.0
#: Street View が返す最大サイズ（無料枠でも 640x640 まで）
MAX_IMAGE_EDGE = 640


def is_configured() -> bool:
    return bool(get_settings().google_maps_server_api_key)


async def fetch_image(
    *,
    lat: float,
    lng: float,
    size: int = MAX_IMAGE_EDGE,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes | None:
    """指定地点のストリートビュー画像（正方形）を返す。取得できなければ None。"""
    settings = get_settings()
    key = settings.google_maps_server_api_key
    if not key:
        logger.info("GOOGLE_MAPS_SERVER_API_KEY が未設定のためストリートビューを取得しません")
        return None

    edge = min(size, MAX_IMAGE_EDGE)
    location = f"{lat},{lng}"
    params = {"location": location, "key": key}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, transport=transport) as client:
        try:
            # メタデータは課金対象外。まずパノラマの有無とキーの有効性を確認する
            meta_response = await client.get(METADATA_URL, params=params)
            meta = meta_response.json() if meta_response.status_code < 300 else {}
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("ストリートビューの確認に失敗しました", extra={"error": str(exc)})
            return None

        status = str(meta.get("status", ""))
        if status != "OK":
            logger.info(
                "ストリートビューを利用できません",
                extra={"status": status or "UNKNOWN", "detail": meta.get("error_message", "")},
            )
            return None

        try:
            image_response = await client.get(
                IMAGE_URL,
                params={**params, "size": f"{edge}x{edge}", "fov": "90", "pitch": "0"},
            )
        except httpx.HTTPError as exc:
            logger.warning("ストリートビュー画像の取得に失敗しました", extra={"error": str(exc)})
            return None

    if image_response.status_code >= 300 or not image_response.content:
        logger.warning(
            "ストリートビュー画像を取得できませんでした",
            extra={"status": image_response.status_code},
        )
        return None
    return image_response.content
