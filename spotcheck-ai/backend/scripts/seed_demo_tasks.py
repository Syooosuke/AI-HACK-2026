"""デモ用の依頼（投稿）のシード。

    cd backend && python -m scripts.seed_demo_tasks

一覧・いいね欄・タグの見え方を確認するための投稿を投入する。
固定UUIDなので何度実行しても同じ依頼になり、重複しない。

- 依頼主は `demo_company`（`scripts.seed_demo_users` で作られる）
- **AI審査は通さず、審査済み（open）の状態で直接投入する。** 画面の確認が目的のため
- SOLD / HOT / NEW のタグが1つずつ出るようにデータを作る
- サムネイルは投入後に生成する（ストリートビュー・画像生成が未設定ならプレースホルダ）
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.models import Task, TaskStatus
from app.services import thumbnail_service

CLIENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

#: (UUID, タイトル, 詳細, 緯度, 経度, 住所, 報酬, 人数, status, 閲覧数, 経過時間h)
DEMO_TASKS: list[tuple] = [
    (
        "aaaa1111-0000-4000-8000-000000000001",
        "店舗前の行列の状況を確認",
        (
            "店舗の入口前に並んでいる人数と待ち列の長さが分かるように、店の正面から全体を撮影してください。"
            "列の最後尾がどこまで伸びているかも分かるようにしてください。"
        ),
        35.6595,
        139.7005,
        "東京都渋谷区道玄坂1丁目",
        1500,
        1,
        TaskStatus.OPEN,
        3,
        0,
    ),
    (
        "aaaa1111-0000-4000-8000-000000000002",
        "駐車場の利用状況を確認",
        (
            "駐車区画の埋まり具合と空きスペースの位置が分かるように、駐車場全体を撮影してください。"
            "入口からの見通しも分かるようにしてください。"
        ),
        35.6812,
        139.7671,
        "東京都千代田区丸の内1丁目",
        2000,
        2,
        TaskStatus.OPEN,
        24,  # HOT の閾値（既定20）を超える
        30,  # NEW は消える
    ),
    (
        "aaaa1111-0000-4000-8000-000000000003",
        "工事の進捗状況を確認",
        (
            "工事箇所の進み具合と足場・重機の配置が分かるように、正面から全体を撮影してください。"
            "周辺の歩行者と車の通行状況も分かるようにしてください。"
        ),
        35.6586,
        139.7454,
        "東京都港区芝公園4丁目",
        3000,
        1,
        TaskStatus.OPEN,
        8,
        2,
    ),
    (
        "aaaa1111-0000-4000-8000-000000000004",
        "花の開花状況を確認",
        (
            "咲き具合が分かるように、木や花壇の全体と花の付き方の両方が見えるように撮影してください。"
            "散り始めているかも分かるようにしてください。"
        ),
        35.7148,
        139.7967,
        "東京都台東区浅草2丁目",
        1200,
        1,
        TaskStatus.OPEN,
        2,
        1,
    ),
    (
        "aaaa1111-0000-4000-8000-000000000005",
        "路面と積雪の状況を確認",
        (
            "路面の凍結や積雪の程度が分かるように、歩道と車道の両方を含めて撮影してください。"
            "通行できる幅が残っているかも分かるようにしてください。"
        ),
        35.6938,
        139.7036,
        "東京都新宿区西新宿1丁目",
        2500,
        1,
        TaskStatus.COMPLETED,  # SOLD タグの確認用
        15,
        50,
    ),
]


def upsert_tasks() -> list[uuid.UUID]:
    now = datetime.now(UTC)
    factory = get_session_factory()
    created: list[uuid.UUID] = []

    with factory() as session:
        for (
            raw_id,
            title,
            description,
            lat,
            lng,
            address,
            reward,
            worker_count,
            status,
            view_count,
            age_hours,
        ) in DEMO_TASKS:
            task_id = uuid.UUID(raw_id)
            task = session.get(Task, task_id)
            values = {
                "client_id": CLIENT_ID,
                "title": title,
                "description": description,
                "location_lat": lat,
                "location_lng": lng,
                "location_address": address,
                "scheduled_at": now + timedelta(hours=1),
                "deadline_at": now + timedelta(days=2),
                "reward_amount": reward,
                "required_worker_count": worker_count,
                "status": status,
                "review_score": 85,
                "review_summary": f"{title}。撮影条件は具体的で、危険性や撮影禁止の懸念はありません。",
                "view_count": view_count,
                "created_at": now - timedelta(hours=age_hours),
                "approved_worker_count": 1 if status is TaskStatus.COMPLETED else 0,
            }
            if task is None:
                session.add(Task(id=task_id, **values))
                action = "作成"
            else:
                for key, value in values.items():
                    setattr(task, key, value)
                action = "更新"
            created.append(task_id)
            print(f"  {action}: {title}（{address}） {status.value}")
        session.commit()
    return created


async def main() -> int:
    settings = get_settings()
    print(
        f"デモ依頼を投入します（HOTの閾値: 閲覧{settings.hot_view_count}回 / NEW: {settings.new_task_hours}時間以内）"
    )
    task_ids = upsert_tasks()

    print("サムネイルを生成します…")
    for task_id in task_ids:
        await thumbnail_service.generate_for_task(task_id, force=True)

    print(f"デモ依頼 {len(task_ids)} 件を投入しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
