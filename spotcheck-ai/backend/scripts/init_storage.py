"""Storage バケットの初期化（Phase 0 作業5）。

    cd backend && python -m scripts.init_storage

- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` が設定されていれば Supabase 上に
  2つの**非公開**バケットを作成する（既存ならそのまま）。
- 未設定の場合はローカル保存用ディレクトリを作成し、その旨を表示する。
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import get_settings
from app.core.exceptions import StorageError
from app.core.storage import get_storage


async def main() -> int:
    settings = get_settings()
    storage = get_storage()
    print(f"ストレージ実装: {storage.name}")
    if storage.name == "local":
        print(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY が未設定のため、"
            f"ローカル保存（{settings.local_storage_dir}）を初期化します。"
        )

    try:
        results = await storage.ensure_buckets()
    except StorageError as exc:
        print(f"失敗: {exc.message}", file=sys.stderr)
        if exc.details:
            print(f"  詳細: {exc.details}", file=sys.stderr)
        return 1
    finally:
        await storage.close()

    for bucket, result in results.items():
        label = {"created": "作成しました", "exists": "既に存在します"}.get(result, result)
        print(f"  {bucket}: {label}（非公開 / 署名URL配信）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
