"""FastAPI アプリ本体。CORS・例外ハンドラ・ルーター登録・起動時チェックを担う。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, files, health, social, submissions, tasks
from app.core.config import collect_config_warnings, get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger, setup_logging
from app.core.storage import get_storage
from app.jobs import expire_tasks
from app.services.orca_client import get_orca_client

setup_logging()
logger = get_logger(__name__)

#: 期限超過タスクのクローズ間隔（docs/03-api.md 4.1）
EXPIRE_JOB_INTERVAL_MINUTES = 5


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "SpotCheck AI バックエンドを起動します",
        extra={
            "app_env": settings.app_env,
            "storage_backend": settings.effective_storage_backend,
            "orca_stub_mode": settings.orca_stub_enabled,
        },
    )

    # 不足している環境変数を警告する（Phase 0 完了条件。起動は止めない）
    warnings = collect_config_warnings(settings)
    if warnings:
        logger.warning("環境変数が不足しています", extra={"count": len(warnings)})
        for warning in warnings:
            logger.warning(warning.format())
    else:
        logger.info("環境変数の設定は充足しています")

    # 期限超過タスクのクローズ（docs/03-api.md 4節）。
    # 起動直後に1回実行し、停止中に期限切れになったタスクを回収する。
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        expire_tasks.run_once,
        trigger="interval",
        minutes=EXPIRE_JOB_INTERVAL_MINUTES,
        id="expire_tasks",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    expire_tasks.run_once()
    logger.info(
        "期限切れタスクのジョブを登録しました",
        extra={"interval_minutes": EXPIRE_JOB_INTERVAL_MINUTES},
    )

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await get_orca_client().close()
        await get_storage().close()
        logger.info("SpotCheck AI バックエンドを停止しました")


app = FastAPI(
    title="SpotCheck AI API",
    version="0.1.0",
    description="現地撮影代行プラットフォーム SpotCheck AI のバックエンド",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(submissions.router)
app.include_router(social.router)
app.include_router(files.router)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "アプリ例外", extra={"code": exc.code, "path": request.url.path, "status": exc.status_code}
    )
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI のバリデーションエラーを docs/03-api.md 1.2 の形式へ変換する。"""
    fields = {
        ".".join(str(part) for part in error["loc"][1:]): error["msg"] for error in exc.errors()
    }
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "入力内容に誤りがあります。",
                "details": {"fields": fields},
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """FastAPI 標準の HTTPException もエラー形式を統一する。"""
    code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(
        exc.status_code, "HTTP_ERROR"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": str(exc.detail), "details": {}}},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("想定外のエラー", extra={"path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "サーバー内部でエラーが発生しました。",
                "details": {},
            }
        },
    )
