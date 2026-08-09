"""デモユーザーのシード（docs/02-database.md 4節 / D-06）。

    cd backend && python -m scripts.seed_demo_users

固定UUIDを使うため何度実行しても同じユーザーになる（既存なら値を更新する）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.db import get_session_factory
from app.models import User, UserRole

DEMO_USERS: list[dict[str, object]] = [
    {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "role": UserRole.CLIENT,
        "display_name": "デモ株式会社",
        "email": "client@example.com",
        "trust_score": Decimal("50.0"),
    },
    {
        "id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "role": UserRole.WORKER,
        "display_name": "山田 太郎",
        "email": "yamada@example.com",
        "trust_score": Decimal("92.0"),
    },
    {
        "id": uuid.UUID("33333333-3333-3333-3333-333333333333"),
        "role": UserRole.WORKER,
        "display_name": "佐藤 花子",
        "email": "sato@example.com",
        "trust_score": Decimal("78.0"),
    },
    {
        "id": uuid.UUID("44444444-4444-4444-4444-444444444444"),
        "role": UserRole.WORKER,
        "display_name": "鈴木 一郎",
        "email": "suzuki@example.com",
        "trust_score": Decimal("55.0"),
    },
]


def main() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        for spec in DEMO_USERS:
            user = session.get(User, spec["id"])
            if user is None:
                session.add(User(**spec))
                action = "作成"
            else:
                user.role = spec["role"]
                user.display_name = spec["display_name"]
                user.email = spec["email"]
                user.trust_score = spec["trust_score"]
                action = "更新"
            print(f"  {action}: {spec['display_name']} ({spec['role'].value}) {spec['id']}")
        session.commit()
    print(f"デモユーザー {len(DEMO_USERS)} 名を投入しました。")


if __name__ == "__main__":
    main()
