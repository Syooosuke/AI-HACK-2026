"""notifications と worker_reviews のヘッドを統合する

並行して開発された2つの機能がそれぞれリビジョンを追加したため、
ヘッドが2本に分岐した。スキーマ変更は無く、履歴を1本へ戻すだけ。

Revision ID: 335d3aa1b952
Revises: 1938a8d17ebf, a21c8e34f901
Create Date: 2026-08-14 00:45:26.759522

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "335d3aa1b952"
down_revision: str | None = ("1938a8d17ebf", "a21c8e34f901")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
