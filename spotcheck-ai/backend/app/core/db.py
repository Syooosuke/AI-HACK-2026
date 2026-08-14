"""SQLAlchemy の Engine / Session。

`.env` が無くてもアプリが起動できるよう、Engine は遅延生成する（import 時に接続しない）。
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# 到達不能なホストが設定されていた場合にリクエストが長時間ぶら下がるのを防ぐ
_CONNECT_TIMEOUT_SECONDS = 5


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("postgresql"):
        connect_args["connect_timeout"] = _CONNECT_TIMEOUT_SECONDS
    if settings.database_url.startswith("postgresql+psycopg"):
        # **サーバー側のプリペアドステートメントを使わない。**
        #
        # 本番は Supabase の transaction pooler（PgBouncer, 6543番）を経由する。
        # このモードでは1トランザクションごとに背後の接続が切り替わるため、
        # 「別の接続で作ったプリペアドステートメント」を参照して次のエラーになる。
        #
        #   psycopg.errors.InvalidSqlStatementName:
        #     prepared statement "_pg3_1" does not exist
        #
        # psycopg3 は既定で同じSQLを5回実行するとプリペアドに切り替える
        # （prepare_threshold=5）。そのため**最初の数回は成功し、その後だけ失敗する**
        # という分かりにくい壊れ方をする。None にすると常に切り替えない。
        #
        # 直接接続（ローカル開発）でも None で問題なく、失うのは小さな最適化だけ。
        connect_args["prepare_threshold"] = None
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
        echo=False,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI の依存関係として使うセッション。"""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection() -> tuple[bool, str | None]:
    """DBへ到達できるかを確認する。(成功か, エラー内容) を返す。"""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001 - 接続不能でもアプリは動かし続ける
        return False, f"{type(exc).__name__}: {exc}"
