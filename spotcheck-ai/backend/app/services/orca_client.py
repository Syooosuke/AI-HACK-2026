"""AI呼び出しの唯一の窓口（docs/04-ai-pipeline.md 1節）。

Phase 1 では**スタブモードのみ**を実装する。実HTTP呼び出し（1.1節の OpenAI互換API）は
Phase 3 で実装する。呼び出し側のコードは変更不要な設計にしてある。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.exceptions import AIServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)

Purpose = Literal["task_review", "image_validation", "environment_check", "result_summary"]
Tier = Literal["light", "vision"]

STUB_MODEL_NAME = "stub"


@dataclass
class ImageInput:
    """OrcaRouterへ渡す画像。Phase 3 で base64 データURIに変換して送る。"""

    url: str | None = None
    base64_data: str | None = None
    media_type: str = "image/jpeg"

    def to_log_payload(self) -> str:
        """ログには base64 を残さない（docs/04-ai-pipeline.md 1.3）。"""
        return self.url or "<image omitted>"


@dataclass
class OrcaResult:
    parsed: BaseModel
    raw: dict[str, Any]
    #: 実際に使われたモデル名（スタブ時は "stub"）
    model: str
    latency_ms: int
    is_stub: bool


class InvocationRecorder(Protocol):
    """`ai_invocations` への記録を行う呼び出し可能オブジェクト。"""

    def __call__(
        self,
        *,
        purpose: str,
        related_type: str | None,
        related_id: uuid.UUID | None,
        model: str | None,
        request_payload: dict[str, Any] | None,
        response_payload: dict[str, Any] | None,
        latency_ms: int | None,
        is_stub: bool,
        error: str | None,
    ) -> None: ...


class OrcaClient:
    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def is_stub(self) -> bool:
        return self._settings.orca_stub_enabled

    async def complete_json(
        self,
        *,
        purpose: Purpose,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        images: list[ImageInput] | None = None,
        tier: Tier = "light",
        related_type: str | None = None,
        related_id: uuid.UUID | None = None,
        recorder: InvocationRecorder | None = None,
        context: dict[str, Any] | None = None,
    ) -> OrcaResult:
        """JSONを返すAI呼び出し。`response_schema` でバリデートした結果を返す。

        `context` はスタブ応答の分岐に使う補助情報（例: `attempt_no`）。
        実呼び出しでは送信せず、監査ログにのみ含める。
        """
        started = time.perf_counter()
        request_payload = self._build_log_payload(
            purpose=purpose,
            tier=tier,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            images=images,
            context=context,
        )

        try:
            if self.is_stub:
                raw = _stub_response(purpose, context or {})
                model = STUB_MODEL_NAME
                is_stub = True
            else:
                # TODO(phase-3): docs/04-ai-pipeline.md 1.1 の OpenAI互換API を httpx で呼ぶ。
                # リトライ（429/5xx/タイムアウト/JSONパース失敗）とJSON強制の4段階もここで実装する。
                raise AIServiceError(
                    "OrcaRouter への実呼び出しは Phase 3 で実装します。"
                    "現在は ORCA_STUB_MODE=true または ORCA_API_KEY 未設定でのみ動作します。"
                )

            parsed = response_schema.model_validate(raw)
        except AIServiceError as exc:
            self._record(
                recorder,
                purpose=purpose,
                related_type=related_type,
                related_id=related_id,
                model=None,
                request_payload=request_payload,
                response_payload=None,
                latency_ms=_elapsed_ms(started),
                is_stub=self.is_stub,
                error=exc.message,
            )
            raise
        except ValidationError as exc:
            message = f"AIの応答がスキーマに一致しませんでした: {exc.error_count()} 件"
            self._record(
                recorder,
                purpose=purpose,
                related_type=related_type,
                related_id=related_id,
                model=None,
                request_payload=request_payload,
                response_payload=None,
                latency_ms=_elapsed_ms(started),
                is_stub=self.is_stub,
                error=message,
            )
            raise AIServiceError(message) from exc

        latency_ms = _elapsed_ms(started)
        self._record(
            recorder,
            purpose=purpose,
            related_type=related_type,
            related_id=related_id,
            model=model,
            request_payload=request_payload,
            response_payload=raw,
            latency_ms=latency_ms,
            is_stub=is_stub,
            error=None,
        )
        return OrcaResult(
            parsed=parsed, raw=raw, model=model, latency_ms=latency_ms, is_stub=is_stub
        )

    def router_name(self, tier: Tier) -> str:
        """`model` に渡すルーター名。モデル名をコードへ直書きしない（1.1節）。"""
        return (
            self._settings.orca_router_vision
            if tier == "vision"
            else self._settings.orca_router_light
        )

    def _build_log_payload(
        self,
        *,
        purpose: Purpose,
        tier: Tier,
        system_prompt: str,
        user_prompt: str,
        images: list[ImageInput] | None,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "purpose": purpose,
            "tier": tier,
            "model": self.router_name(tier),
            "systemPrompt": system_prompt,
            "userPrompt": user_prompt,
            "images": [image.to_log_payload() for image in images or []],
            "context": context or {},
        }

    def _record(self, recorder: InvocationRecorder | None, **kwargs: Any) -> None:
        if recorder is None:
            return
        try:
            recorder(**kwargs)
        except Exception:
            logger.exception("ai_invocations への記録に失敗しました")

    async def close(self) -> None:
        """Phase 3 で httpx.AsyncClient を保持したら、ここで解放する。"""


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _stub_response(purpose: Purpose, context: dict[str, Any]) -> dict[str, Any]:
    """固定応答（docs/04-ai-pipeline.md 1.4）。

    `image_validation` を提出回数の奇偶で交互に失敗させるのは、
    **デモで再撮影ループを見せるため**である。この挙動は変更しないこと。
    """
    if purpose == "task_review":
        return {
            "decision": "approved",
            "score": 85,
            "safety": "pass",
            "validity": "pass",
            "risk": "pass",
            "duplication": "pass",
            "rejection_reason": None,
            "missing_info": [],
            "summary": "現地の状況を撮影して確認する依頼です。",
        }

    if purpose == "image_validation":
        attempt_no = int(context.get("attempt_no", 1))
        if attempt_no % 2 == 1:
            return {
                "score": 45,
                "subject_present": True,
                "framing_ok": True,
                "sharpness_ok": True,
                "brightness_ok": False,
                "reference_match": None,
                "observed_scene": "夕方の街路と建設中の建物",
                "daylight_state": "twilight",
                "weather_hint": "cloudy",
                "issues": [
                    {"code": "TOO_DARK", "message": "暗すぎます。明るい場所で撮影してください"}
                ],
                "summary": "対象は写っていますが露出が不足しています。",
            }
        return {
            "score": 88,
            "subject_present": True,
            "framing_ok": True,
            "sharpness_ok": True,
            "brightness_ok": True,
            "reference_match": None,
            "observed_scene": "日中の街路と建設中の建物",
            "daylight_state": "daylight",
            "weather_hint": "clear",
            "issues": [],
            "summary": "工事は予定通り進行中。安全対策は適切に実施されています。",
        }

    if purpose == "environment_check":
        return {"consistent": True, "note": "画像内の光の状態は撮影時刻と矛盾しない"}

    return {"summary": "工事は予定通り進行中。安全対策は適切に実施されています。"}


@lru_cache
def get_orca_client() -> OrcaClient:
    return OrcaClient()
