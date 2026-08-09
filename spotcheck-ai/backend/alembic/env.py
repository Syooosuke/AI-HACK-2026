"""Alembic の実行環境。

接続文字列は `alembic.ini` ではなく環境変数（`DATABASE_URL`）から読む。
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings
from app.core.db import get_engine
from app.models import Base  # 全モデルを登録するため app.models 経由で import する

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
