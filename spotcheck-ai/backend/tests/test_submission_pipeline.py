"""検品パイプラインのテスト（docs/04-ai-pipeline.md 3.4, 6節）。

VLM の応答だけを差し替え、合否判定・issues の付与・reality_score の保存を検証する。
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AssignmentStatus, Submission, Task, User, ValidationStatus
from app.repositories import submission_repo
from app.services import submission_pipeline, submission_service
from app.services.orca_client import OrcaClient
from tests.conftest import auth_headers, make_assignment, make_task, store_raw_image

BASE_LAT, BASE_LNG = 35.6595, 139.7005


def vlm_output(**overrides: Any) -> str:
    payload = {
        "score": 88,
        "subject_present": True,
        "framing_ok": True,
        "sharpness_ok": True,
        "brightness_ok": True,
        "reference_match": None,
        "observed_scene": "日中の街路と建設中の建物",
        # 環境整合の判定を実行時刻に依存させないため unknown を既定にする
        "daylight_state": "unknown",
        "weather_hint": "clear",
        "issues": [],
        "summary": "工事は予定通り進行中です。",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def install_vlm(monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_stub_mode", False)
    monkeypatch.setattr(settings, "orca_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        system_prompt = request_body["messages"][0]["content"]
        response_content = (
            json.dumps(
                {"summary": "提出画像では、日中の街路と建設中の建物が確認できます。"},
                ensure_ascii=False,
            )
            # 総括生成か画像検品かは system_prompt でしか見分けられない。
            # 文面を変えたらここも直す（一致しないと検品側の応答が総括に混ざる）
            if "依頼したクライアントへ報告" in system_prompt
            else content
        )
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "model": "vision-model",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": response_content}}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            },
        )

    client = OrcaClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(submission_pipeline, "get_orca_client", lambda: client)
    monkeypatch.setattr(submission_service, "get_orca_client", lambda: client)


def submit_and_validate(
    session: Session,
    users: dict[str, User],
    monkeypatch: pytest.MonkeyPatch,
    *,
    vlm: str,
    lat: float = BASE_LAT,
    lng: float = BASE_LNG,
    **submission_overrides: Any,
) -> Submission:
    install_vlm(monkeypatch, vlm)
    task = make_task(session, client=users["client"])
    assignment = make_assignment(session, task=task, worker=users["worker"])
    key = f"{task.id}/{assignment.id}/1.jpg"
    store_raw_image(key)

    now = datetime.now(UTC)
    fields: dict[str, Any] = {
        "captured_lat": lat,
        "captured_lng": lng,
        "captured_at": now,
        "received_at": now,
        "captured_accuracy_m": 12.0,
        **submission_overrides,
    }
    submission = Submission(
        assignment_id=assignment.id,
        task_id=task.id,
        worker_id=users["worker"].id,
        attempt_no=1,
        raw_image_url=key,
        ai_validation_status=ValidationStatus.PENDING,
        **fields,
    )
    submission_repo.create(session, submission)
    assignment.status = AssignmentStatus.SUBMITTED
    session.commit()

    asyncio.run(submission_pipeline.run_validation(submission.id))
    session.expire_all()
    return submission


# ----------------------------------------------------------------------
def test_matching_image_is_approved(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    submission = submit_and_validate(session, users, monkeypatch, vlm=vlm_output())

    assert submission.ai_validation_status is ValidationStatus.APPROVED
    assert submission.ai_score == 88
    assert submission.ai_feedback["issues"] == []
    assert submission.reality_score == 100
    assert submission.location_check["within_tolerance"] is True
    assert submission.processed_image_url is not None
    task = session.get(Task, submission.task_id)
    assert task is not None
    assert task.result_summary == "提出画像では、日中の街路と建設中の建物が確認できます。"


def test_legacy_fixed_summary_is_regenerated_when_results_are_opened(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """既存データの固定総括も、結果画面の取得時にOrcaRouterで置き換える。"""
    from fastapi.testclient import TestClient

    from app.main import app

    submission = submit_and_validate(session, users, monkeypatch, vlm=vlm_output())
    task = session.get(Task, submission.task_id)
    assert task is not None
    task.result_summary = "工事は予定通り進行中。安全対策は適切に実施されています。"
    session.commit()

    with TestClient(app) as api:
        response = api.get(
            f"/api/tasks/{task.id}/results",
            headers=auth_headers(users["client"]),
        )

    assert response.status_code == 200
    assert response.json()["resultSummary"] == (
        "提出画像では、日中の街路と建設中の建物が確認できます。"
    )


def test_unrelated_image_fails_with_subject_missing(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """依頼内容と無関係な画像は SUBJECT_MISSING で不合格になる。"""
    submission = submit_and_validate(
        session,
        users,
        monkeypatch,
        vlm=vlm_output(
            score=20,
            subject_present=False,
            observed_scene="湖と山の風景",
            issues=[{"code": "SUBJECT_MISSING", "message": "依頼された対象が写っていません"}],
            summary="依頼された工事現場は写っていません。",
        ),
    )

    assert submission.ai_validation_status is ValidationStatus.REJECTED
    assert [issue["code"] for issue in submission.ai_feedback["issues"]] == ["SUBJECT_MISSING"]
    assert submission.ai_feedback["checks"]["subject_present"] is False


def test_subject_missing_fails_even_with_high_score(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """subject_present が false ならスコアに関わらず不合格（docs 3.4）。"""
    submission = submit_and_validate(
        session, users, monkeypatch, vlm=vlm_output(score=95, subject_present=False)
    )
    assert submission.ai_validation_status is ValidationStatus.REJECTED


def test_person_in_frame_does_not_cause_rejection(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """対象が写っている場合、人物・顔の写り込みだけでは不合格にしない。"""
    submission = submit_and_validate(
        session,
        users,
        monkeypatch,
        vlm=vlm_output(
            score=30,
            subject_present=True,
            framing_ok=False,
            observed_scene="建物の外壁と屋根、その手前にいる人物",
            issues=[
                {
                    "code": "OTHER",
                    "message": "人物を避け、外壁や屋根の劣化状態が分かる近景を撮影してください",
                }
            ],
            summary="建物は写っていますが人物が邪魔で詳細が確認できません。",
        ),
    )

    assert submission.ai_validation_status is ValidationStatus.APPROVED
    assert submission.ai_score == get_settings().submission_score_threshold
    assert submission.ai_feedback["checks"]["framing_ok"] is True
    assert submission.ai_feedback["issues"] == []


def test_rough_photo_passes_when_the_subject_is_readable(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """構図・ピント・明るさが不十分でも、対象が写っていてスコアが足りれば合格する。

    現地で1枚撮るだけのワーカーに、構図と写りの良さまで求めると依頼が達成できない。
    **合否を決めるのは対象の有無とスコアであり、この3つのフラグではない**ことを固定する
    （docs/04-ai-pipeline.md 3.2「判定の基本方針」）。
    """
    threshold = get_settings().submission_score_threshold
    submission = submit_and_validate(
        session,
        users,
        monkeypatch,
        vlm=vlm_output(
            score=threshold,
            subject_present=True,
            framing_ok=False,
            sharpness_ok=False,
            brightness_ok=False,
            issues=[],
        ),
    )

    assert submission.ai_validation_status is ValidationStatus.APPROVED
    assert submission.ai_feedback["issues"] == []


@pytest.mark.parametrize(
    ("code", "message", "overrides"),
    [
        ("TOO_DARK", "暗すぎます", {"brightness_ok": False}),
        ("TOO_BLURRY", "ピントが合っていません", {"sharpness_ok": False}),
        ("ANGLE_MISMATCH", "別アングルで撮影してください", {"framing_ok": False}),
    ],
)
def test_quality_issues_are_rejected_with_their_code(
    session: Session,
    users: dict[str, User],
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    message: str,
    overrides: dict[str, Any],
) -> None:
    submission = submit_and_validate(
        session,
        users,
        monkeypatch,
        vlm=vlm_output(score=45, issues=[{"code": code, "message": message}], **overrides),
    )

    assert submission.ai_validation_status is ValidationStatus.REJECTED
    assert [issue["code"] for issue in submission.ai_feedback["issues"]] == [code]


def test_location_mismatch_is_added_by_service_layer(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """依頼地点から200m以上離れた座標なら、画像が良くても LOCATION_MISMATCH で不合格。"""
    submission = submit_and_validate(
        session,
        users,
        monkeypatch,
        vlm=vlm_output(),  # 画像自体は88点で問題なし
        lat=BASE_LAT + 0.0027,  # 約300m north
    )

    assert submission.ai_validation_status is ValidationStatus.REJECTED
    assert "LOCATION_MISMATCH" in [issue["code"] for issue in submission.ai_feedback["issues"]]
    assert submission.location_check["within_tolerance"] is False
    # 距離不一致で40点減点
    assert submission.reality_score == 60


def test_timestamp_mismatch_is_added_by_service_layer(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    submission = submit_and_validate(
        session,
        users,
        monkeypatch,
        vlm=vlm_output(),
        captured_at=now - timedelta(seconds=400),
    )

    assert submission.ai_validation_status is ValidationStatus.REJECTED
    assert "TIMESTAMP_MISMATCH" in [issue["code"] for issue in submission.ai_feedback["issues"]]
    assert submission.reality_score == 75  # -25


def test_exif_conflict_reduces_reality_score_without_failing(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """EXIFのGPS矛盾は減点のみで、合否には影響しない。"""
    submission = submit_and_validate(
        session,
        users,
        monkeypatch,
        vlm=vlm_output(),
        exif_data={"gps_lat": 34.7, "gps_lng": 135.5},
    )

    assert submission.ai_validation_status is ValidationStatus.APPROVED
    assert submission.location_check["exif_gps_conflict"] is True
    assert submission.reality_score == 80  # -20


def test_environment_mismatch_reduces_reality_score(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """撮影時刻と画像の光の状態が矛盾すると減点される（C-5）。"""
    # 日本時間 14:00 に撮影したと申告し、画像は夜という応答にする
    captured = datetime.now(UTC).replace(hour=5, minute=0)
    submission = submit_and_validate(
        session,
        users,
        monkeypatch,
        vlm=vlm_output(daylight_state="night"),
        captured_at=captured,
        received_at=captured,
    )

    environment = submission.location_check["environment_consistency"]
    assert environment["expected_daylight"] is True
    assert environment["consistent"] is False
    assert "ENVIRONMENT_MISMATCH" in submission.location_check["flags"]
    # 環境矛盾 -20（時刻ずれが出る場合は追加減点されるため上限で確認）
    assert submission.reality_score <= 80


def test_client_api_never_exposes_the_raw_bucket(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """クライアント向けAPIのレスポンスに原本（STORAGE_BUCKET_RAW）が一切現れない。

    キー自体は加工後画像と同じパスを使うため、**バケット名**で機械的に検証する。
    """
    from fastapi.testclient import TestClient

    from app.main import app

    submission = submit_and_validate(session, users, monkeypatch, vlm=vlm_output())
    assert submission.ai_validation_status is ValidationStatus.APPROVED
    settings = get_settings()

    client_headers = auth_headers(users["client"])
    worker_headers = auth_headers(users["worker"])
    with TestClient(app) as api:
        submission_status = api.get(f"/api/submissions/{submission.id}", headers=worker_headers)
        bodies = [
            api.get(f"/api/tasks/{submission.task_id}/results", headers=client_headers).text,
            api.get(f"/api/tasks/{submission.task_id}", headers=client_headers).text,
            api.get(f"/api/submissions/{submission.id}", headers=client_headers).text,
            submission_status.text,
        ]

    # プライバシー対象が0件でも、マスキング工程が完了していれば成功表示にする。
    assert submission.masking_result["regions"] == []
    assert submission_status.json()["checks"]["privacyMasked"] is True

    for body in bodies:
        assert settings.storage_bucket_raw not in body
    # 配信用バケットの署名URLは含まれる（結果画面で表示するため）
    assert settings.storage_bucket_processed in bodies[0]


def test_local_processed_image_is_served_but_raw_image_is_forbidden(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ローカル保存でも加工済み画像を表示でき、原本は同じAPIから取得できない。"""
    from fastapi.testclient import TestClient

    from app.main import app

    submission = submit_and_validate(session, users, monkeypatch, vlm=vlm_output())
    settings = get_settings()
    headers = auth_headers(users["client"])

    with TestClient(app) as api:
        result = api.get(f"/api/tasks/{submission.task_id}/results", headers=headers).json()
        image_url = result["results"][0]["processedImageUrl"]
        processed = api.get(image_url)
        raw = api.get(f"/api/files/{settings.storage_bucket_raw}/{submission.raw_image_url}")

    assert processed.status_code == 200
    assert processed.headers["content-type"] == "image/jpeg"
    assert processed.content.startswith(b"\xff\xd8")
    assert raw.status_code == 403


def test_ai_failure_marks_error_without_consuming_retake(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI呼び出しを失敗させると error になり、再撮影回数は消費されない。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_stub_mode", False)
    monkeypatch.setattr(settings, "orca_api_key", "test-key")
    failing = OrcaClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(401, text="Invalid token"))
    )
    monkeypatch.setattr(submission_pipeline, "get_orca_client", lambda: failing)

    task = make_task(session, client=users["client"])
    assignment = make_assignment(session, task=task, worker=users["worker"])
    key = f"{task.id}/{assignment.id}/1.jpg"
    store_raw_image(key)
    now = datetime.now(UTC)
    submission = Submission(
        assignment_id=assignment.id,
        task_id=task.id,
        worker_id=users["worker"].id,
        attempt_no=1,
        raw_image_url=key,
        captured_lat=BASE_LAT,
        captured_lng=BASE_LNG,
        captured_at=now,
        received_at=now,
        ai_validation_status=ValidationStatus.PENDING,
    )
    submission_repo.create(session, submission)
    assignment.status = AssignmentStatus.SUBMITTED
    session.commit()

    asyncio.run(submission_pipeline.run_validation(submission.id))
    session.expire_all()

    assert submission.ai_validation_status is ValidationStatus.ERROR
    assert assignment.retake_count == 0
    assert assignment.status is AssignmentStatus.ACCEPTED
    assert submission.ai_feedback["issues"][0]["code"] == "OTHER"
