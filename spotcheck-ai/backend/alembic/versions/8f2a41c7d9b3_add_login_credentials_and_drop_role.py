"""ログインID・パスワードを追加し、role を廃止する

1アカウントで「依頼する」「撮影する」の両方を行えるようにするため、
users から role を削除し、認証用の login_id / password_hash を追加する。

既存行の password_hash には照合不能な値（`!`）を入れる。
デモユーザーのパスワードは `python -m scripts.seed_demo_users` で設定する。

Revision ID: 8f2a41c7d9b3
Revises: 3237be2160d3
Create Date: 2026-08-11 12:40:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8f2a41c7d9b3"
down_revision: str | None = "3237be2160d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: bcrypt ハッシュとして成立しない値。この値のままではログインできない。
UNUSABLE_PASSWORD_HASH = "!"


def upgrade() -> None:
    # 1. まず NULL 許可で追加し、既存行を埋めてから NOT NULL にする
    op.add_column("users", sa.Column("login_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(), nullable=True))

    # 2. 既存行のバックフィル。login_id は id の先頭8桁から生成し一意性を担保する
    op.execute(
        sa.text(
            """
            UPDATE users
               SET login_id = 'user_' || substr(replace(id::text, '-', ''), 1, 8)
             WHERE login_id IS NULL
            """
        )
    )
    op.execute(
        sa.text("UPDATE users SET password_hash = :hash WHERE password_hash IS NULL").bindparams(
            hash=UNUSABLE_PASSWORD_HASH
        )
    )

    # 3. 制約を付ける
    op.alter_column("users", "login_id", nullable=False)
    op.alter_column("users", "password_hash", nullable=False)
    op.create_index(op.f("ix_users_login_id"), "users", ["login_id"], unique=True)

    # 4. role を廃止する（権限は「依頼のオーナーか受注者か」で判定する）
    op.drop_column("users", "role")
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # role を復活させる。値の判別はできないため、依頼を作成したことがあるユーザーを client とする
    user_role = sa.Enum("client", "worker", name="user_role")
    user_role.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column("role", user_role, nullable=False, server_default="worker"),
    )
    op.execute(
        sa.text(
            """
            UPDATE users
               SET role = 'client'
             WHERE id IN (SELECT DISTINCT client_id FROM tasks)
            """
        )
    )
    op.alter_column("users", "role", server_default=None)

    op.drop_index(op.f("ix_users_login_id"), table_name="users")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "login_id")
