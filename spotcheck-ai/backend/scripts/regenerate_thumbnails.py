"""投稿サムネイルの再生成。

    cd backend && python -m scripts.regenerate_thumbnails            # 未生成の分だけ
    cd backend && python -m scripts.regenerate_thumbnails --force    # 既存も作り直す

サムネイルの意匠を変えたときや、ストリートビュー・画像生成のキーを後から設定したときに使う。
参考画像が付いている依頼はその画像を使うため、実質的に何も変わらない。
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.db import get_session_factory
from app.models import Task, TaskStatus
from app.services import thumbnail_service

#: 一覧に並ぶ可能性がある status のみ対象にする（却下・取消は作らない）
TARGET_STATUSES = (
    TaskStatus.OPEN,
    TaskStatus.IN_PROGRESS,
    TaskStatus.COMPLETED,
    TaskStatus.EXPIRED,
)


async def main(force: bool) -> int:
    factory = get_session_factory()
    with factory() as session:
        tasks = list(
            session.scalars(
                select(Task).where(Task.status.in_(TARGET_STATUSES)).order_by(Task.created_at)
            )
        )
        targets = [task for task in tasks if force or task.thumbnail_image_url is None]
        print(f"対象: {len(targets)} 件（全 {len(tasks)} 件中）")
        ids_and_titles = [(task.id, task.title) for task in targets]

    for task_id, title in ids_and_titles:
        await thumbnail_service.generate_for_task(task_id, force=force)
        with factory() as session:
            task = session.get(Task, task_id)
            source = task.thumbnail_source if task else "?"
        print(f"  {title[:24]:26} → {source}")

    print("完了しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(force="--force" in sys.argv)))
