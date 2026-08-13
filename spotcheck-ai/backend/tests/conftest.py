"""テスト共通のセットアップ。

- 専用のテストDB（`<開発DB名>_test_<チェックアウトのハッシュ>`）を作成し、
  `alembic upgrade head` を適用する。マイグレーション自体もテストで検証されることになる。
  DB名をチェックアウトごとに分けるのは、複数の git worktree が同じDBを取り合って
  alembic のリビジョンが食い違うのを防ぐため。
- ストレージはローカルバックエンドへ固定し、Supabaseへは接続しない。
- テストごとに全テーブルを TRUNCATE し、デモユーザーを再投入する。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# ---- アプリを import する前に環境変数を差し替える --------------------------------
_DEV_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://postgres:password@localhost:5432/spotcheck"
)
_BASE_URL, _, _DEV_DB = _DEV_URL.rpartition("/")

# テストDBはチェックアウト（git worktree）ごとに分ける。
# 同じDBを複数のブランチで共有すると、片方のマイグレーションで stamp された状態を
# もう片方が解決できず `Can't locate revision` で全滅する。
_CHECKOUT_ID = hashlib.sha1(str(Path(__file__).resolve().parents[2]).encode()).hexdigest()[:8]
TEST_DB_NAME = os.environ.get("TEST_DATABASE_NAME", f"{_DEV_DB}_test_{_CHECKOUT_ID}")
TEST_DATABASE_URL = f"{_BASE_URL}/{TEST_DB_NAME}"

_STORAGE_DIR = Path(tempfile.mkdtemp(prefix="spotcheck-test-storage-"))

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = str(_STORAGE_DIR)
os.environ["ORCA_STUB_MODE"] = "true"
os.environ["ORCA_API_KEY"] = ""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_engine, get_session_factory
from app.core.security import create_access_token, hash_password
from app.models import Base, Task, TaskAssignment, User

TABLES_IN_TRUNCATE_ORDER = (
    "worker_reviews",
    "payments",
    "ai_invocations",
    "submissions",
    "task_assignments",
    "task_reference_images",
    "tasks",
    "users",
)

CLIENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
WORKER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
WORKER2_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

#: テスト用の共通パスワード。ハッシュ化のコストを抑えるため使い回す。
TEST_PASSWORD = "test-password"
_TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    """テストDBを作成し、マイグレーションを適用する。"""
    admin_url = f"{_BASE_URL}/postgres"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()

    # 設定・エンジンのキャッシュを破棄してテストDBを指させる
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    assert get_settings().database_url == TEST_DATABASE_URL

    from alembic.config import Config

    from alembic import command

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        command.upgrade(config, "head")
    except Exception:  # noqa: BLE001 - 解決できない状態なら作り直して復旧する
        # テストDBは全ブランチで共有される。別ブランチのマイグレーションで
        # stamp されていると `Can't locate revision` で失敗するため、
        # スキーマごと作り直してから当ブランチのマイグレーションを当て直す。
        with get_engine().begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        command.upgrade(config, "head")

    yield

    get_engine().dispose()


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    """各テストの前に全テーブルを空にする。"""
    with get_engine().begin() as conn:
        conn.execute(
            text(f"TRUNCATE {', '.join(TABLES_IN_TRUNCATE_ORDER)} RESTART IDENTITY CASCADE")
        )
    yield


@pytest.fixture
def session() -> Iterator[Session]:
    factory = get_session_factory()
    with factory() as db:
        yield db


@pytest.fixture
def users(session: Session) -> dict[str, User]:
    """テスト用ユーザーを投入する。

    role は廃止したため、どのユーザーも依頼の作成と受注の両方ができる。
    キー名（client / worker）はテスト内での役割の区別であって権限ではない。
    """
    created = {
        "client": User(
            id=CLIENT_ID,
            login_id="demo_company",
            password_hash=_TEST_PASSWORD_HASH,
            display_name="デモ株式会社",
            email="c@example.com",
        ),
        "worker": User(
            id=WORKER_ID,
            login_id="yamada",
            password_hash=_TEST_PASSWORD_HASH,
            display_name="山田 太郎",
            email="w1@example.com",
            trust_score=92,
        ),
        "worker2": User(
            id=WORKER2_ID,
            login_id="sato",
            password_hash=_TEST_PASSWORD_HASH,
            display_name="佐藤 花子",
            email="w2@example.com",
            trust_score=78,
        ),
    }
    session.add_all(created.values())
    session.commit()
    return created


def auth_headers(user: User | uuid.UUID) -> dict[str, str]:
    """指定ユーザーとしてAPIを叩くための Authorization ヘッダーを作る。"""
    user_id = user if isinstance(user, uuid.UUID) else user.id
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def make_task(
    session: Session,
    *,
    client: User,
    status: str = "open",
    required_worker_count: int = 1,
    deadline_offset_hours: float = 6,
) -> Task:
    from app.models import TaskStatus

    now = datetime.now(UTC)
    task = Task(
        client_id=client.id,
        title="駅前の再開発工事の進捗確認",
        description="工事の進捗と周辺の交通状況が分かるように正面から撮影してください。",
        location_lat=35.6595,
        location_lng=139.7005,
        location_address="東京都渋谷区道玄坂1丁目",
        scheduled_at=now + timedelta(minutes=30),
        deadline_at=now + timedelta(hours=deadline_offset_hours),
        reward_amount=2000,
        required_worker_count=required_worker_count,
        status=TaskStatus(status),
        review_score=85,
    )
    session.add(task)
    session.commit()
    return task


def make_assignment(session: Session, *, task: Task, worker: User) -> TaskAssignment:
    assignment = TaskAssignment(task_id=task.id, worker_id=worker.id)
    session.add(assignment)
    session.commit()
    return assignment


def tiny_jpeg(
    size: tuple[int, int] = (64, 48), color: tuple[int, int, int] = (120, 140, 160)
) -> bytes:
    """検品テスト用の小さな実JPEG（Pillow で開ける必要がある）。"""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def store_raw_image(key: str, bucket: str | None = None) -> None:
    """ローカルストレージに検品用の画像を置く。"""
    settings = get_settings()
    path = _STORAGE_DIR / (bucket or settings.storage_bucket_raw) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tiny_jpeg())


__all__ = [
    "CLIENT_ID",
    "TEST_PASSWORD",
    "WORKER2_ID",
    "WORKER_ID",
    "Base",
    "auth_headers",
    "make_assignment",
    "make_task",
    "store_raw_image",
]
