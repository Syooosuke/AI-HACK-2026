"""Google Street View Static API から現地画像を取得する。

サーバー側の専用キー（`GOOGLE_MAPS_SERVER_API_KEY`）を使う。
フロント用のキーはブラウザに露出させる前提でリファラー制限をかけるため、
サーバーからは使えないので分けている。

キー未設定・API未有効・パノラマが存在しない地点では `None` を返す。
呼び出し側はプレースホルダへフォールバックする。

**一時的な失敗（タイムアウト・5xx・接続エラー）だけ再試行する。**
`ZERO_RESULTS` のような恒久的な結果を再試行しても同じ答えしか返らず、
待ち時間と課金が無駄になるため区別している。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"
REQUEST_TIMEOUT_SECONDS = 15.0
#: Street View が返す最大サイズ（無料枠でも 640x640 まで）
MAX_IMAGE_EDGE = 640

#: 一時的な失敗のときの待ち時間（秒）。要素数＝再試行の回数。
#: 画像取得は呼ぶたびに課金されるため、回数は増やしすぎない。
BACKOFF_SECONDS = (1.0, 2.0)

#: 再試行しても結果が変わらない status（パノラマが無い・キーが拒否されている等）
PERMANENT_STATUSES = frozenset(
    {
        "ZERO_RESULTS",
        "NOT_FOUND",
        "REQUEST_DENIED",
        "INVALID_REQUEST",
        "OVER_QUERY_LIMIT",
    }
)


@dataclass
class _Outcome:
    """1回の試行の結果。`retryable` が True のときだけ再試行する。"""

    image: bytes | None = None
    retryable: bool = False
    reason: str = ""


def is_configured() -> bool:
    return bool(get_settings().google_maps_server_api_key)


async def fetch_image(
    *,
    lat: float,
    lng: float,
    size: int = MAX_IMAGE_EDGE,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes | None:
    """指定地点のストリートビュー画像（正方形）を返す。取得できなければ None。

    一時的な失敗は `BACKOFF_SECONDS` の回数だけ再試行する。
    """
    settings = get_settings()
    key = settings.google_maps_server_api_key
    if not key:
        logger.info("GOOGLE_MAPS_SERVER_API_KEY が未設定のためストリートビューを取得しません")
        return None

    edge = min(size, MAX_IMAGE_EDGE)
    params = {"location": f"{lat},{lng}", "key": key}
    max_attempts = len(BACKOFF_SECONDS) + 1

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, transport=transport) as client:
        for attempt in range(1, max_attempts + 1):
            outcome = await _try_once(client, params=params, edge=edge)
            if outcome.image is not None:
                return outcome.image
            if not outcome.retryable or attempt == max_attempts:
                return None

            wait_seconds = BACKOFF_SECONDS[attempt - 1]
            logger.info(
                "ストリートビューの取得を再試行します",
                extra={
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "wait_seconds": wait_seconds,
                    "reason": outcome.reason,
                },
            )
            await asyncio.sleep(wait_seconds)
    return None


async def _try_once(client: httpx.AsyncClient, *, params: dict[str, str], edge: int) -> _Outcome:
    """メタデータ確認 → 画像取得を1回だけ行う。"""
    # メタデータは課金対象外。まずパノラマの有無とキーの有効性を確認する
    try:
        meta_response = await client.get(METADATA_URL, params=params)
    except httpx.HTTPError as exc:
        return _Outcome(retryable=True, reason=f"metadata: {exc}")

    if meta_response.status_code >= 500:
        return _Outcome(retryable=True, reason=f"metadata status={meta_response.status_code}")

    try:
        meta = meta_response.json() if meta_response.status_code < 300 else {}
    except ValueError as exc:
        return _Outcome(retryable=True, reason=f"metadata parse: {exc}")

    status = str(meta.get("status", ""))
    if status != "OK":
        permanent = status in PERMANENT_STATUSES
        logger.info(
            "ストリートビューを利用できません",
            extra={
                "status": status or "UNKNOWN",
                "detail": meta.get("error_message", ""),
                "permanent": permanent,
            },
        )
        # 未知の status は一時的な障害の可能性があるため再試行する
        return _Outcome(retryable=not permanent, reason=f"status={status or 'UNKNOWN'}")

    try:
        image_response = await client.get(
            IMAGE_URL,
            params={**params, "size": f"{edge}x{edge}", "fov": "90", "pitch": "0"},
        )
    except httpx.HTTPError as exc:
        return _Outcome(retryable=True, reason=f"image: {exc}")

    if image_response.status_code >= 500 or not image_response.content:
        return _Outcome(
            retryable=True,
            reason=f"image status={image_response.status_code} bytes={len(image_response.content)}",
        )
    if image_response.status_code >= 300:
        logger.warning(
            "ストリートビュー画像を取得できませんでした",
            extra={"status": image_response.status_code},
        )
        return _Outcome(retryable=False, reason=f"image status={image_response.status_code}")

    return _Outcome(image=image_response.content)
