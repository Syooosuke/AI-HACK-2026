"""スキーマ共通の基底クラス。

JSONキーは camelCase、Python側は snake_case とする（docs/03-api.md 1.3）。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """レスポンス/リクエストの基底。camelCase のエイリアスを自動生成する。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
