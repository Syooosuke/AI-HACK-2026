"""Phase 0 の完了条件に対応するテスト。

- `.env` が無くてもアプリが起動し、`GET /api/health` が 200 を返す
- 不足している環境変数が警告として列挙される
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings, collect_config_warnings
from app.main import app


def test_health_returns_200() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert "storage" in body["dependencies"]
    assert "orca" in body["dependencies"]


def test_config_warnings_listed_when_env_is_empty() -> None:
    """環境変数が空でも Settings は生成でき、不足分が警告として返る。"""
    settings = Settings(
        _env_file=None,
        supabase_url="",
        supabase_service_role_key="",
        orca_api_key="",
    )
    warnings = collect_config_warnings(settings)
    variables = {name for warning in warnings for name in warning.variables}

    assert "SUPABASE_URL" in variables
    assert "ORCA_API_KEY" in variables
    # ストレージは local、AI はスタブへフォールバックする
    assert settings.effective_storage_backend == "local"
    assert settings.orca_stub_enabled is True


def test_unknown_path_returns_unified_error_shape() -> None:
    with TestClient(app) as client:
        response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
