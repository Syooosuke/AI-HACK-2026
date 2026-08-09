"""機能C: 位置偽装（Spoofing）対策（docs/04-ai-pipeline.md 4節）。

**LLM任せにせず、まず決定論的な計算を行う。**

| # | チェック | 不合格条件 | 影響 |
|---|---|---|---|
| C-1 | 依頼地点との距離 | > LOCATION_TOLERANCE_METERS | 合否に直結 |
| C-2 | 端末時刻とサーバー受信時刻の差 | > TIMESTAMP_TOLERANCE_SECONDS | 合否に直結 |
| C-3 | 撮影希望日時との差 | ±6時間超 | 減点のみ（警告） |
| C-4 | EXIFのGPSと申告座標の距離 | > 200m | 減点のみ |
| C-5 | 画像の光の状態と撮影時刻 | 矛盾 | 減点のみ |
| C-6 | Geolocation の精度 | > 500m | 減点のみ（警告） |
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.geo import haversine_meters
from app.models import Submission, Task
from app.services.exif import exif_datetime

JST = ZoneInfo("Asia/Tokyo")

#: C-3 撮影希望日時からの許容差
SCHEDULE_TOLERANCE = timedelta(hours=6)
#: C-4 EXIFのGPSと申告座標の許容差
EXIF_GPS_TOLERANCE_METERS = 200.0
#: C-6 Geolocation の精度の警告しきい値
ACCURACY_WARNING_METERS = 500.0

#: C-5 の簡易日中判定。astral を導入せず「6時〜18時を daylight」とする（4.1節で許容）
DAYLIGHT_START_HOUR = 6
DAYLIGHT_END_HOUR = 18

#: Reality Score の減点ルール（docs/04-ai-pipeline.md 4.2）
PENALTY_DISTANCE = 40
PENALTY_TIMESTAMP = 25
PENALTY_EXIF_CONFLICT = 20
PENALTY_ENVIRONMENT = 20
PENALTY_SCHEDULE_WARNING = 5
PENALTY_ACCURACY_WARNING = 5
PENALTY_LOW_TRUST = 10
LOW_TRUST_THRESHOLD = Decimal(50)

# flags に入れるコード
FLAG_DISTANCE = "DISTANCE_EXCEEDED"
FLAG_TIMESTAMP = "TIMESTAMP_DRIFT"
FLAG_SCHEDULE = "SCHEDULE_DRIFT"
FLAG_EXIF_CONFLICT = "EXIF_GPS_CONFLICT"
FLAG_ACCURACY = "LOW_ACCURACY"
FLAG_ENVIRONMENT = "ENVIRONMENT_MISMATCH"

#: 画像から観測した光の状態 → 日中かどうか（unknown / indoor は判定不能）
_DAYLIGHT_OBSERVATION = {
    "daylight": True,
    "twilight": False,
    "night": False,
    "indoor": None,
    "unknown": None,
}


def run_deterministic_checks(task: Task, submission: Submission) -> dict[str, Any]:
    """C-1〜C-4, C-6 を評価し、submissions.location_check に保存する構造を返す。"""
    settings = get_settings()
    flags: list[str] = []

    # C-1 距離検証
    distance_m = haversine_meters(
        task.location_lat, task.location_lng, submission.captured_lat, submission.captured_lng
    )
    within_tolerance = distance_m <= settings.location_tolerance_meters
    if not within_tolerance:
        flags.append(FLAG_DISTANCE)

    # C-2 時刻整合（端末の申告時刻とサーバー受信時刻の差）
    delta_seconds = abs(
        (_aware(submission.received_at) - _aware(submission.captured_at)).total_seconds()
    )
    timestamp_consistent = delta_seconds <= settings.timestamp_tolerance_seconds
    if not timestamp_consistent:
        flags.append(FLAG_TIMESTAMP)

    # C-3 撮影時間帯（警告のみ）
    schedule_delta = abs(
        (_aware(submission.captured_at) - _aware(task.scheduled_at)).total_seconds()
    )
    schedule_within_window = schedule_delta <= SCHEDULE_TOLERANCE.total_seconds()
    if not schedule_within_window:
        flags.append(FLAG_SCHEDULE)

    # C-4 EXIF照合（GPSが無いこと自体は不合格にしない）
    exif_gps = _exif_gps(submission)
    exif_gps_conflict = False
    exif_distance_m: float | None = None
    if exif_gps is not None:
        exif_distance_m = haversine_meters(
            exif_gps[0], exif_gps[1], submission.captured_lat, submission.captured_lng
        )
        exif_gps_conflict = exif_distance_m > EXIF_GPS_TOLERANCE_METERS
        if exif_gps_conflict:
            flags.append(FLAG_EXIF_CONFLICT)

    # C-6 精度チェック（警告のみ）
    accuracy = submission.captured_accuracy_m
    accuracy_ok = accuracy is None or accuracy <= ACCURACY_WARNING_METERS
    if not accuracy_ok:
        flags.append(FLAG_ACCURACY)

    return {
        "distance_m": round(distance_m, 1),
        "within_tolerance": within_tolerance,
        "timestamp_delta_seconds": int(delta_seconds),
        "timestamp_consistent": timestamp_consistent,
        "schedule_delta_seconds": int(schedule_delta),
        "schedule_within_window": schedule_within_window,
        "exif_gps_present": exif_gps is not None,
        "exif_gps_conflict": exif_gps_conflict,
        "exif_gps_distance_m": None if exif_distance_m is None else round(exif_distance_m, 1),
        "exif_datetime": _exif_datetime_text(submission),
        "accuracy_m": accuracy,
        "accuracy_ok": accuracy_ok,
        # C-5 は画像検品（機能B）の出力を使うため、この時点では未評価
        "environment_consistency": None,
        "flags": flags,
    }


def apply_environment_check(
    payload: dict[str, Any], submission: Submission, daylight_state: str
) -> dict[str, Any]:
    """C-5 環境整合。VLM が観測した光の状態と撮影時刻の整合を見る（減点のみ）。

    日出没は外部APIを使わず「6時〜18時を daylight」とする簡易判定（4.1節で許容されている）。
    """
    captured_jst = _aware(submission.captured_at).astimezone(JST)
    expected_daylight = DAYLIGHT_START_HOUR <= captured_jst.hour < DAYLIGHT_END_HOUR
    observed_daylight = _DAYLIGHT_OBSERVATION.get(daylight_state)

    if observed_daylight is None:
        note = "画像から光の状態を判定できなかったため、整合チェックは行わない"
        consistent: bool | None = None
    elif observed_daylight == expected_daylight:
        note = "画像内の光の状態は撮影時刻と矛盾しない"
        consistent = True
    else:
        note = (
            f"撮影時刻は{'日中' if expected_daylight else '夜間'}だが、"
            f"画像は{'日中' if observed_daylight else '夜間'}のように見える"
        )
        consistent = False

    payload["environment_consistency"] = {
        "expected_daylight": expected_daylight,
        "observed_daylight": observed_daylight,
        "daylight_state": daylight_state,
        "consistent": consistent,
        "note": note,
        "method": "simple_hour_range_6_18",
    }
    if consistent is False and FLAG_ENVIRONMENT not in payload["flags"]:
        payload["flags"].append(FLAG_ENVIRONMENT)
    return payload


def compute_reality_score(payload: dict[str, Any], *, worker_trust_score: Decimal) -> int:
    """信頼度スコア（docs/04-ai-pipeline.md 4.2）。基礎100点から減点し 0〜100 にクリップする。"""
    score = 100
    if not payload.get("within_tolerance", True):
        score -= PENALTY_DISTANCE
    if not payload.get("timestamp_consistent", True):
        score -= PENALTY_TIMESTAMP
    if payload.get("exif_gps_conflict"):
        score -= PENALTY_EXIF_CONFLICT
    environment = payload.get("environment_consistency") or {}
    if environment.get("consistent") is False:
        score -= PENALTY_ENVIRONMENT
    if not payload.get("schedule_within_window", True):
        score -= PENALTY_SCHEDULE_WARNING
    if not payload.get("accuracy_ok", True):
        score -= PENALTY_ACCURACY_WARNING
    if worker_trust_score < LOW_TRUST_THRESHOLD:
        score -= PENALTY_LOW_TRUST
    return max(0, min(100, score))


def _exif_gps(submission: Submission) -> tuple[float, float] | None:
    exif = submission.exif_data or {}
    lat, lng = exif.get("gps_lat"), exif.get("gps_lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return float(lat), float(lng)
    return None


def _exif_datetime_text(submission: Submission) -> str | None:
    value = exif_datetime(submission.exif_data)
    return None if value is None else value.isoformat()


def _aware(value: datetime) -> datetime:
    """timestamptz で保存しているためUTC付きで返るが、念のため補正する。"""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
