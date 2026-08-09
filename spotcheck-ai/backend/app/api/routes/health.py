"""ヘルスチェック（docs/03-api.md 2節）。

`.env` が未設定でも 200 を返す。各依存先の状態は `dependencies` に載せ、
不足があれば `status="degraded"` として示す（起動可否とは切り離す）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from app.core.config import collect_config_warnings, get_settings
from app.core.db import check_connection
from app.core.storage import get_storage

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
def health() -> dict[str, Any]:
    """アプリの稼働確認。外部への通信は行わないため即座に返る。"""
    settings = get_settings()
    warnings = collect_config_warnings(settings)
    return {
        "status": "ok" if not warnings else "degraded",
        "appEnv": settings.app_env,
        "time": datetime.now(UTC).isoformat(),
        "dependencies": {
            "database": {"configured": True, "url": _mask_dsn(settings.database_url)},
            "storage": {
                "backend": get_storage().name,
                "bucketRaw": settings.storage_bucket_raw,
                "bucketProcessed": settings.storage_bucket_processed,
            },
            "orca": {
                "stubMode": settings.orca_stub_enabled,
                "routerLight": settings.orca_router_light,
                "routerVision": settings.orca_router_vision,
            },
        },
        "configWarnings": [warning.format() for warning in warnings],
    }


@router.get("/db")
def health_db() -> dict[str, Any]:
    """DBへの到達確認。接続できない場合も 200 で詳細を返す（起動を妨げないため）。"""
    ok, error = check_connection()
    return {"status": "ok" if ok else "error", "error": error}


def _mask_dsn(dsn: str) -> str:
    """接続文字列からパスワードを除去する。"""
    if "://" not in dsn:
        return dsn
    scheme, rest = dsn.split("://", 1)
    if "@" not in rest:
        return dsn
    credentials, host = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"
