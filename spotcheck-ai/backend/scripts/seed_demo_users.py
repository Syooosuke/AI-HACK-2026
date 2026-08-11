"""デモユーザーのシード（docs/02-database.md 4節）。

    cd backend && python -m scripts.seed_demo_users

固定UUIDを使うため何度実行しても同じユーザーになる（既存なら値を更新する）。
role は廃止したため、どのアカウントでも「依頼する」「撮影する」の両方ができる。

パスワードは環境変数 `DEMO_USER_PASSWORD` で上書きできる（既定は下記の定数）。
デモ用の共有アカウントなので、本番相当の環境では実行しないこと。
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal

from app.core.db import get_session_factory
from app.core.security import hash_password
from app.models import User

#: デモアカウントの既定パスワード（全アカウント共通）。
DEFAULT_DEMO_PASSWORD = "spotcheck123"

DEMO_USERS: list[dict[str, object]] = [
    {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "login_id": "demo_company",
        "display_name": "デモ株式会社",
        "email": "client@example.com",
        "trust_score": Decimal("50.0"),
    },
    {
        "id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "login_id": "yamada",
        "display_name": "山田 太郎",
        "email": "yamada@example.com",
        "trust_score": Decimal("92.0"),
    },
    {
        "id": uuid.UUID("33333333-3333-3333-3333-333333333333"),
        "login_id": "sato",
        "display_name": "佐藤 花子",
        "email": "sato@example.com",
        "trust_score": Decimal("78.0"),
    },
    {
        "id": uuid.UUID("44444444-4444-4444-4444-444444444444"),
        "login_id": "suzuki",
        "display_name": "鈴木 一郎",
        "email": "suzuki@example.com",
        "trust_score": Decimal("55.0"),
    },
]


def main() -> None:
    password = os.getenv("DEMO_USER_PASSWORD") or DEFAULT_DEMO_PASSWORD
    session_factory = get_session_factory()
    with session_factory() as session:
        for spec in DEMO_USERS:
            # パスワードは実行ごとに再ハッシュする（ソルトが変わるだけで挙動は同じ）
            password_hash = hash_password(password)
            user = session.get(User, spec["id"])
            if user is None:
                session.add(User(**spec, password_hash=password_hash))
                action = "作成"
            else:
                user.login_id = spec["login_id"]
                user.display_name = spec["display_name"]
                user.email = spec["email"]
                user.trust_score = spec["trust_score"]
                user.password_hash = password_hash
                action = "更新"
            print(f"  {action}: {spec['display_name']}（ログインID: {spec['login_id']}）")
        session.commit()
    print(f"デモユーザー {len(DEMO_USERS)} 名を投入しました。パスワードは全員 `{password}` です。")


if __name__ == "__main__":
    main()
