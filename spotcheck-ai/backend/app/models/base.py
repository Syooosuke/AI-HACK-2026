"""SQLAlchemy の宣言的基底クラス。

Alembic の autogenerate はこの `Base.metadata` を参照する。
Phase 1 で各モデルを追加したら、`app/models/__init__.py` から import してここに集約すること
（import されていないモデルはマイグレーションに含まれない）。
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
