"""ワーカー評価UI確認用の合格済み提出を投入する。

    cd backend && ./.venv/bin/python -m scripts.seed_worker_review_demo

AI審査・受注・撮影・画像検品を通さず、`demo_company` で結果詳細を開くための
データを直接作る。何度実行しても同じデータを更新し、既存の評価は削除するため、
評価フォームを繰り返し確認できる。開発環境以外では実行しないこと。
"""

from __future__ import annotations

import asyncio
import io
import uuid
from datetime import UTC, datetime, timedelta

from PIL import Image, ImageDraw

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.storage import get_storage
from app.models import (
    AssignmentStatus,
    Submission,
    Task,
    TaskAssignment,
    TaskStatus,
    User,
    ValidationStatus,
    WorkerReview,
)

CLIENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
WORKER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
TASK_ID = uuid.UUID("eeee1111-0000-4000-8000-000000000001")
ASSIGNMENT_ID = uuid.UUID("eeee2222-0000-4000-8000-000000000001")
SUBMISSION_ID = uuid.UUID("eeee3333-0000-4000-8000-000000000001")
PROCESSED_KEY = f"review-demo/{SUBMISSION_ID}.jpg"


def build_demo_image() -> bytes:
    image = Image.new("RGB", (1200, 800), (226, 232, 240))
    draw = ImageDraw.Draw(image)
    draw.rectangle((90, 180, 1110, 700), fill=(203, 213, 225), outline=(100, 116, 139), width=6)
    draw.rectangle((180, 300, 500, 700), fill=(148, 163, 184))
    draw.rectangle((590, 250, 1000, 700), fill=(100, 116, 139))
    draw.text((90, 80), "SpotCheck AI - Worker Review Demo", fill=(30, 41, 59))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


async def main() -> int:
    settings = get_settings()
    if settings.app_env != "development":
        raise RuntimeError("このシードは development 環境でのみ実行できます。")

    storage = get_storage()
    await storage.ensure_buckets()
    await storage.upload(
        bucket=settings.storage_bucket_processed,
        key=PROCESSED_KEY,
        data=build_demo_image(),
        content_type="image/jpeg",
    )

    now = datetime.now(UTC)
    with get_session_factory()() as session:
        if session.get(User, CLIENT_ID) is None or session.get(User, WORKER_ID) is None:
            raise RuntimeError("先に scripts.seed_demo_users を実行してください。")

        task = session.get(Task, TASK_ID)
        task_values = {
            "client_id": CLIENT_ID,
            "title": "ワーカー評価UIの確認用依頼",
            "description": "駅前施設の外観が分かるように、正面から全景を撮影してください。",
            "location_lat": 35.6595,
            "location_lng": 139.7005,
            "location_address": "東京都渋谷区道玄坂1丁目",
            "scheduled_at": now - timedelta(hours=2),
            "deadline_at": now + timedelta(days=1),
            "reward_amount": 2000,
            "required_worker_count": 1,
            "approved_worker_count": 1,
            "status": TaskStatus.COMPLETED,
            "review_score": 90,
            "review_summary": "撮影条件が明確な依頼です。",
            "result_summary": "施設の外観と周辺状況を確認できました。",
        }
        if task is None:
            task = Task(id=TASK_ID, **task_values)
            session.add(task)
        else:
            for key, value in task_values.items():
                setattr(task, key, value)
        session.flush()

        assignment = session.get(TaskAssignment, ASSIGNMENT_ID)
        if assignment is None:
            assignment = TaskAssignment(
                id=ASSIGNMENT_ID,
                task_id=TASK_ID,
                worker_id=WORKER_ID,
            )
            session.add(assignment)
        assignment.status = AssignmentStatus.APPROVED
        assignment.completed_at = now
        session.flush()

        submission = session.get(Submission, SUBMISSION_ID)
        submission_values = {
            "assignment_id": ASSIGNMENT_ID,
            "task_id": TASK_ID,
            "worker_id": WORKER_ID,
            "attempt_no": 1,
            "raw_image_url": "review-demo/not-exposed.jpg",
            "processed_image_url": PROCESSED_KEY,
            "captured_lat": 35.6595,
            "captured_lng": 139.7005,
            "captured_accuracy_m": 8.0,
            "captured_at": now - timedelta(hours=1),
            "received_at": now - timedelta(hours=1),
            "ai_validation_status": ValidationStatus.APPROVED,
            "ai_score": 92,
            "ai_feedback": {
                "summary": "施設正面の外観と周辺の歩行状況が確認できます。",
                "issues": [],
            },
            "location_check": {
                "within_tolerance": True,
                "timestamp_consistent": True,
                "distance_m": 3.2,
            },
            "masking_result": {"regions": [], "skipped": False},
            "reality_score": 96,
        }
        if submission is None:
            session.add(Submission(id=SUBMISSION_ID, **submission_values))
        else:
            for key, value in submission_values.items():
                setattr(submission, key, value)

        # 再実行時は未評価のフォームへ戻す。
        review = session.query(WorkerReview).filter_by(submission_id=SUBMISSION_ID).one_or_none()
        if review is not None:
            session.delete(review)
        session.commit()

    print("ワーカー評価UI確認用データを投入しました。")
    print(f"依頼ID: {TASK_ID}")
    print(f"提出ID: {SUBMISSION_ID}")
    print("demo_company / spotcheck123 でログインし、次のURLを開いてください。")
    print(f"http://localhost:3000/requests/{TASK_ID}/results/{SUBMISSION_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
