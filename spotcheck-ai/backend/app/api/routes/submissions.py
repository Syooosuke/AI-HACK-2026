"""提出系エンドポイント（docs/03-api.md 3.6, 3.7）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.core.storage import get_storage
from app.schemas.submission import SubmissionCreateResponse, SubmissionStatusResponse
from app.services import submission_pipeline, submission_service
from app.services.submission_service import SubmissionInput

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


@router.post("", response_model=SubmissionCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_submission(
    session: DbSession,
    worker: CurrentUser,
    background_tasks: BackgroundTasks,
    assignment_id: Annotated[uuid.UUID, Form(alias="assignmentId")],
    captured_lat: Annotated[float, Form(alias="capturedLat", ge=-90, le=90)],
    captured_lng: Annotated[float, Form(alias="capturedLng", ge=-180, le=180)],
    captured_at: Annotated[datetime, Form(alias="capturedAt")],
    image: Annotated[UploadFile, File()],
    captured_accuracy_m: Annotated[float | None, Form(alias="capturedAccuracyM")] = None,
    device_info: Annotated[str | None, Form(alias="deviceInfo")] = None,
) -> SubmissionCreateResponse:
    """画像＋メタデータの提出（D-02）。検品はバックグラウンドで実行し 202 を返す。"""
    response = await submission_service.create_submission(
        session,
        worker=worker,
        data=SubmissionInput(
            assignment_id=assignment_id,
            captured_lat=captured_lat,
            captured_lng=captured_lng,
            captured_at=captured_at,
            captured_accuracy_m=captured_accuracy_m,
            device_info_raw=device_info,
        ),
        image=image,
        storage=get_storage(),
    )
    # 検品は別セッションで走るため、ここで明示的にコミットして submission を可視化する。
    # （依存関係の teardown によるコミットを待つと BackgroundTasks が先に走り、
    #   検品側から提出レコードが見えないことがある）
    session.commit()
    background_tasks.add_task(submission_pipeline.run_validation, response.submission.id)
    return response


@router.get("/{submission_id}", response_model=SubmissionStatusResponse)
async def get_submission(
    session: DbSession, user: CurrentUser, submission_id: uuid.UUID
) -> SubmissionStatusResponse:
    """検品状況・結果のポーリング（画面⑦⑧）。"""
    return await submission_service.get_submission_status(
        session, user=user, submission_id=submission_id, storage=get_storage()
    )
