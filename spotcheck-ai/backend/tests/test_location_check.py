"""位置偽装対策と Reality Score のテスト（docs/04-ai-pipeline.md 4節）。"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from PIL import Image

from app.models import Submission, Task
from app.services import location_check
from app.services.exif import extract_exif

BASE_LAT, BASE_LNG = 35.6595, 139.7005
NOW = datetime(2026, 8, 10, 5, 0, tzinfo=UTC)  # 日本時間 14:00（日中）


def make_task(**overrides) -> Task:
    task = Task(
        title="駅前の再開発工事の進捗確認",
        description="工事全景を撮影してください。",
        location_lat=BASE_LAT,
        location_lng=BASE_LNG,
        scheduled_at=NOW,
        deadline_at=NOW + timedelta(hours=6),
        reward_amount=2000,
        required_worker_count=1,
    )
    for key, value in overrides.items():
        setattr(task, key, value)
    return task


def make_submission(**overrides) -> Submission:
    submission = Submission(
        attempt_no=1,
        raw_image_url="k.jpg",
        captured_lat=BASE_LAT,
        captured_lng=BASE_LNG,
        captured_at=NOW,
        received_at=NOW + timedelta(seconds=5),
        captured_accuracy_m=12.0,
    )
    for key, value in overrides.items():
        setattr(submission, key, value)
    return submission


# ----------------------------------------------------------------------
# C-1 距離 / C-2 時刻
# ----------------------------------------------------------------------
def test_c1_within_tolerance() -> None:
    payload = location_check.run_deterministic_checks(make_task(), make_submission())
    assert payload["within_tolerance"] is True
    assert payload["distance_m"] == 0.0
    assert payload["flags"] == []


def test_c1_far_away_is_flagged() -> None:
    """依頼地点から離れた座標（約300m）は許容外になる。"""
    payload = location_check.run_deterministic_checks(
        make_task(), make_submission(captured_lat=BASE_LAT + 0.0027)
    )
    assert payload["within_tolerance"] is False
    assert payload["distance_m"] > 200
    assert location_check.FLAG_DISTANCE in payload["flags"]


def test_c2_timestamp_drift_is_flagged() -> None:
    payload = location_check.run_deterministic_checks(
        make_task(), make_submission(received_at=NOW + timedelta(seconds=400))
    )
    assert payload["timestamp_consistent"] is False
    assert location_check.FLAG_TIMESTAMP in payload["flags"]


# ----------------------------------------------------------------------
# C-3 撮影時間帯 / C-6 精度
# ----------------------------------------------------------------------
def test_c3_schedule_drift_is_warning_only() -> None:
    payload = location_check.run_deterministic_checks(
        make_task(),
        make_submission(captured_at=NOW + timedelta(hours=7), received_at=NOW + timedelta(hours=7)),
    )
    assert payload["schedule_within_window"] is False
    assert location_check.FLAG_SCHEDULE in payload["flags"]
    # 合否には影響しない
    assert payload["within_tolerance"] is True
    assert payload["timestamp_consistent"] is True


def test_c6_low_accuracy_is_warning_only() -> None:
    payload = location_check.run_deterministic_checks(
        make_task(), make_submission(captured_accuracy_m=800.0)
    )
    assert payload["accuracy_ok"] is False
    assert location_check.FLAG_ACCURACY in payload["flags"]
    assert payload["within_tolerance"] is True


# ----------------------------------------------------------------------
# C-4 EXIF照合
# ----------------------------------------------------------------------
def test_c4_missing_exif_gps_is_not_a_failure() -> None:
    """ブラウザ撮影ではEXIFにGPSが入らないため、無いこと自体は不合格にしない。"""
    payload = location_check.run_deterministic_checks(make_task(), make_submission())
    assert payload["exif_gps_present"] is False
    assert payload["exif_gps_conflict"] is False
    assert location_check.FLAG_EXIF_CONFLICT not in payload["flags"]


def test_c4_consistent_exif_gps_passes() -> None:
    payload = location_check.run_deterministic_checks(
        make_task(),
        make_submission(exif_data={"gps_lat": BASE_LAT + 0.0005, "gps_lng": BASE_LNG}),
    )
    assert payload["exif_gps_present"] is True
    assert payload["exif_gps_conflict"] is False


def test_c4_conflicting_exif_gps_is_flagged() -> None:
    payload = location_check.run_deterministic_checks(
        make_task(), make_submission(exif_data={"gps_lat": 34.7, "gps_lng": 135.5})
    )
    assert payload["exif_gps_conflict"] is True
    assert location_check.FLAG_EXIF_CONFLICT in payload["flags"]


# ----------------------------------------------------------------------
# C-5 環境整合
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("daylight_state", "expected"),
    [
        ("daylight", True),
        ("twilight", False),
        ("night", False),
        ("indoor", None),
        ("unknown", None),
    ],
)
def test_c5_daytime_capture(daylight_state: str, expected: bool | None) -> None:
    """日本時間14:00の撮影は日中扱い。夜の画像なら矛盾となる。"""
    payload = location_check.run_deterministic_checks(make_task(), make_submission())
    payload = location_check.apply_environment_check(payload, make_submission(), daylight_state)
    environment = payload["environment_consistency"]

    assert environment["expected_daylight"] is True
    assert environment["observed_daylight"] is expected
    if expected is None:
        assert environment["consistent"] is None
        assert location_check.FLAG_ENVIRONMENT not in payload["flags"]
    elif expected:
        assert environment["consistent"] is True
    else:
        assert environment["consistent"] is False
        assert location_check.FLAG_ENVIRONMENT in payload["flags"]


def test_c5_night_capture_with_night_image_is_consistent() -> None:
    night = NOW.replace(hour=15)  # 日本時間 24:00 → 夜間
    submission = make_submission(captured_at=night, received_at=night)
    payload = location_check.run_deterministic_checks(make_task(scheduled_at=night), submission)
    payload = location_check.apply_environment_check(payload, submission, "night")

    assert payload["environment_consistency"]["expected_daylight"] is False
    assert payload["environment_consistency"]["consistent"] is True


# ----------------------------------------------------------------------
# Reality Score（docs/04-ai-pipeline.md 4.2）
# ----------------------------------------------------------------------
def test_reality_score_is_100_when_clean() -> None:
    payload = location_check.run_deterministic_checks(make_task(), make_submission())
    payload = location_check.apply_environment_check(payload, make_submission(), "daylight")
    assert location_check.compute_reality_score(payload, worker_trust_score=Decimal(92)) == 100


@pytest.mark.parametrize(
    ("payload_overrides", "trust", "expected"),
    [
        ({"within_tolerance": False}, 92, 60),  # -40
        ({"timestamp_consistent": False}, 92, 75),  # -25
        ({"exif_gps_conflict": True}, 92, 80),  # -20
        ({"schedule_within_window": False}, 92, 95),  # -5
        ({"accuracy_ok": False}, 92, 95),  # -5
        ({}, 30, 90),  # trust_score < 50 → -10
        # 複合: 距離40 + 時刻25 + EXIF20 + 警告5 + 警告5 + 低信頼10 = 105点減点 → 0でクリップ
        (
            {
                "within_tolerance": False,
                "timestamp_consistent": False,
                "exif_gps_conflict": True,
                "schedule_within_window": False,
                "accuracy_ok": False,
            },
            30,
            0,
        ),
    ],
)
def test_reality_score_penalties(payload_overrides: dict, trust: int, expected: int) -> None:
    payload = location_check.run_deterministic_checks(make_task(), make_submission())
    payload = location_check.apply_environment_check(payload, make_submission(), "daylight")
    payload.update(payload_overrides)
    assert (
        location_check.compute_reality_score(payload, worker_trust_score=Decimal(trust)) == expected
    )


def test_reality_score_environment_penalty() -> None:
    submission = make_submission()
    payload = location_check.run_deterministic_checks(make_task(), submission)
    # 日中の撮影時刻なのに夜の画像 → -20
    payload = location_check.apply_environment_check(payload, submission, "night")
    assert location_check.compute_reality_score(payload, worker_trust_score=Decimal(92)) == 80


# ----------------------------------------------------------------------
# EXIF抽出
# ----------------------------------------------------------------------
def test_extract_exif_returns_none_without_metadata() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), (1, 2, 3)).save(buffer, format="JPEG")
    assert extract_exif(buffer.getvalue()) is None


def test_extract_exif_reads_gps_and_datetime() -> None:
    """GPS付きのJPEGから座標と撮影時刻を取り出せる。"""
    from PIL import ExifTags

    image = Image.new("RGB", (20, 20), (10, 20, 30))
    exif = image.getexif()
    exif[ExifTags.Base.Make.value] = "TestMake"
    exif[ExifTags.Base.Model.value] = "TestModel"
    exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
    exif_ifd[ExifTags.Base.DateTimeOriginal.value] = "2026:08:10 14:30:00"
    gps_ifd = exif.get_ifd(0x8825)
    # 35°39'34.2"N / 139°42'1.8"E（度分秒）
    gps_ifd[1] = "N"
    gps_ifd[2] = (35.0, 39.0, 34.2)
    gps_ifd[3] = "E"
    gps_ifd[4] = (139.0, 42.0, 1.8)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    result = extract_exif(buffer.getvalue())

    assert result is not None
    assert result["make"] == "TestMake"
    assert result["date_time_original"] == "2026:08:10 14:30:00"
    assert result["gps_lat"] == pytest.approx(35.6595, abs=1e-3)
    assert result["gps_lng"] == pytest.approx(139.7005, abs=1e-3)


def test_exif_gps_flows_into_location_check() -> None:
    """抽出したEXIFのGPSが C-4 に渡ることを確認する。"""
    payload = location_check.run_deterministic_checks(
        make_task(),
        make_submission(exif_data={"gps_lat": 35.0, "gps_lng": 139.0, "make": "TestMake"}),
    )
    assert payload["exif_gps_present"] is True
    assert payload["exif_gps_distance_m"] is not None
