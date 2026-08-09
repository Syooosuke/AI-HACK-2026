"""機能C: 位置偽装（Spoofing）対策（docs/04-ai-pipeline.md 4節）。

**LLM任せにせず、まず決定論的な計算を行う。**

Phase 1 では合否判定に直結する C-1（距離）と C-2（時刻整合）のみを実装する。
`GET /api/submissions/{id}` が `checks.location_verified` を返す必要があるため、
この2項目はスタブ化せず実データで判定する。

TODO(phase-4): C-3（撮影時間帯）, C-4（EXIF照合）, C-5（環境整合）, C-6（精度）と
reality_score の算出を実装する。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.core.geo import haversine_meters
from app.models import Submission, Task


def run_deterministic_checks(task: Task, submission: Submission) -> dict[str, Any]:
    """C-1 / C-2 を評価し、submissions.location_check に保存する構造を返す。"""
    settings = get_settings()

    distance_m = haversine_meters(
        task.location_lat, task.location_lng, submission.captured_lat, submission.captured_lng
    )
    within_tolerance = distance_m <= settings.location_tolerance_meters

    delta_seconds = abs(
        (_aware(submission.received_at) - _aware(submission.captured_at)).total_seconds()
    )
    timestamp_consistent = delta_seconds <= settings.timestamp_tolerance_seconds

    flags: list[str] = []
    if not within_tolerance:
        flags.append("DISTANCE_EXCEEDED")
    if not timestamp_consistent:
        flags.append("TIMESTAMP_DRIFT")

    return {
        "distance_m": round(distance_m, 1),
        "within_tolerance": within_tolerance,
        "timestamp_delta_seconds": int(delta_seconds),
        "timestamp_consistent": timestamp_consistent,
        # TODO(phase-4): EXIF照合（C-4）と環境整合（C-5）を実装する
        "exif_gps_present": None,
        "exif_gps_conflict": None,
        "environment_consistency": None,
        "flags": flags,
        "pending_checks": ["C-3", "C-4", "C-5", "C-6"],
    }


def _aware(value: datetime) -> datetime:
    """timestamptz で保存しているためUTC付きで返るが、念のため補正する。"""
    from datetime import UTC

    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
