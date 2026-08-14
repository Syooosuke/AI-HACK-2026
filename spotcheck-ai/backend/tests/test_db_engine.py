"""Engine の接続設定。

**この設定を外すと本番が壊れる**ため、テストで固定する。
経緯は `app/core/db.py` のコメントを参照。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core import db
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_engine_cache():
    """`get_engine` は lru_cache 付きなので、設定を変える前後で必ず捨てる。"""
    db.get_engine.cache_clear()
    yield
    db.get_engine.cache_clear()


def _connect_args_for(url: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """`get_engine` が `create_engine` に渡す connect_args を、接続せずに取り出す。"""
    captured: dict[str, Any] = {}

    def fake_create_engine(_url: str, **kwargs: Any) -> object:
        captured.update(kwargs.get("connect_args") or {})
        return object()

    monkeypatch.setattr(get_settings(), "database_url", url)
    monkeypatch.setattr(db, "create_engine", fake_create_engine)
    db.get_engine()
    return captured


def test_psycopg_disables_server_side_prepared_statements(monkeypatch: pytest.MonkeyPatch) -> None:
    """psycopg 接続では prepare_threshold=None を渡す。

    本番は Supabase の transaction pooler（PgBouncer）経由で、プリペアドを使うと
    `prepared statement "_pg3_1" does not exist` で 500 になる。
    しかも psycopg は同じSQLを5回実行してから切り替えるため、
    **最初の数回は成功してしまい**、テストが無いと壊れたことに気づけない。
    """
    args = _connect_args_for("postgresql+psycopg://u:p@127.0.0.1:6543/postgres", monkeypatch)

    assert "prepare_threshold" in args, (
        "prepare_threshold が渡されていない。"
        "transaction pooler 経由でプリペアドが使われ、本番が断続的に 500 になる"
    )
    assert args["prepare_threshold"] is None
    # 到達不能なホストでリクエストがぶら下がらないようにする既存の設定も維持する
    assert args["connect_timeout"] == db._CONNECT_TIMEOUT_SECONDS


def test_sqlite_does_not_receive_postgres_only_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """PostgreSQL 専用の引数を他のドライバへ渡さない（渡すと接続時に落ちる）。"""
    args = _connect_args_for("sqlite://", monkeypatch)

    assert "prepare_threshold" not in args
    assert "connect_timeout" not in args
