"""AI呼び出しの唯一の窓口（docs/04-ai-pipeline.md 1節）。

OrcaRouter は OpenAI Chat Completions 互換API。OpenAI SDK は使わず httpx で直接呼ぶ。
`model` に渡すのは**ルーター名**であり、モデル名をこのコードへ直書きしてはならない。

`ORCA_STUB_MODE=true` または `ORCA_API_KEY` 未設定のときは HTTP通信を行わず固定応答を返す
（デモ当日の障害対策。最後まで維持する）。
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, Protocol

import httpx
from PIL import Image
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.exceptions import AIServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)

Purpose = Literal[
    "task_review",
    "task_description_generation",
    "image_validation",
    "environment_check",
    "result_summary",
    "thumbnail_generation",
]
Tier = Literal["light", "vision"]

STUB_MODEL_NAME = "stub"
CHAT_COMPLETIONS_PATH = "/chat/completions"

#: 判定のブレを抑えるため審査・検品ともに 0.2 で固定する（docs/04-ai-pipeline.md 1.1）
TEMPERATURE = 0.2
#: 推論モデルへルーティングされると reasoning tokens が上限を食い潰し、本文が空になるため
#: 仕様の 1500 から引き上げている（docs/04-ai-pipeline.md 1.1 の注記）
DEFAULT_MAX_TOKENS = 4000
#: マスキング座標の問い合わせのみ 800（Phase 5 で使用）
COORDINATE_MAX_TOKENS = 800
#: finish_reason="length" のときに上限を倍にして再試行する。その上限値
MAX_TOKENS_CEILING = 8000

#: 送信前に長辺をこのサイズへ縮小し、JPEG品質85で再エンコードする
MAX_IMAGE_LONG_EDGE = 1568
IMAGE_JPEG_QUALITY = 85

#: 指数バックオフの待ち時間（秒）
BACKOFF_SECONDS = (1.0, 2.0)

_JSON_REPAIR_MESSAGE = (
    "直前の出力はJSONとして解析できませんでした。"
    "説明を含めず、JSONオブジェクトのみを出力してください。"
)


@dataclass
class ImageInput:
    """OrcaRouterへ渡す画像。

    Storageの署名URLは有効期限があり、アップストリームから到達できない可能性があるため、
    実際の送信には `base64_data`（`encode_image_for_vlm()` の戻り値）を使う。
    `url` は監査ログ用の参照として保持する。
    """

    url: str | None = None
    base64_data: str | None = None
    media_type: str = "image/jpeg"

    def to_log_payload(self) -> str:
        """ログには base64 を残さない（docs/04-ai-pipeline.md 1.3）。"""
        return self.url or "<image omitted>"

    def to_data_uri(self) -> str:
        if not self.base64_data:
            raise AIServiceError("画像データが空のためAIへ送信できません。")
        return f"data:{self.media_type};base64,{self.base64_data}"


@dataclass
class OrcaResult:
    parsed: BaseModel
    #: 生レスポンス（OpenAI互換のエンベロープ全体）
    raw: dict[str, Any]
    #: 実際に使われたアップストリームのモデル名（スタブ時は "stub"）
    model: str
    latency_ms: int
    is_stub: bool


@dataclass
class GeneratedImage:
    """画像生成の結果。`data` は JPEG/PNG のバイト列。"""

    data: bytes
    model: str
    latency_ms: int


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


def encode_image_for_vlm(data: bytes) -> str:
    """長辺 1568px へ縮小し、JPEG品質85で再エンコードした base64 を返す。

    bbox は正規化座標（0〜1）で扱うため、縮小しても座標の解釈は変わらない。
    """
    with Image.open(io.BytesIO(data)) as image:
        rgb = image.convert("RGB")
        longest = max(rgb.size)
        if longest > MAX_IMAGE_LONG_EDGE:
            scale = MAX_IMAGE_LONG_EDGE / longest
            rgb = rgb.resize(
                (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))),
                Image.LANCZOS,
            )
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=IMAGE_JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class OrcaClient:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = get_settings()
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    @property
    def is_stub(self) -> bool:
        return self._settings.orca_stub_enabled

    def router_name(self, tier: Tier) -> str:
        """`model` に渡すルーター名。モデル名をコードへ直書きしない（1.1節）。"""
        return (
            self._settings.orca_router_vision
            if tier == "vision"
            else self._settings.orca_router_light
        )

    def _http(self) -> httpx.AsyncClient:
        """httpx.AsyncClient はアプリのライフサイクルで使い回す（1.3節）。"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.orca_api_base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self._settings.orca_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self._settings.orca_timeout_seconds,
                transport=self._transport,
            )
        return self._client

    async def complete_json(
        self,
        *,
        purpose: Purpose,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        images: list[ImageInput] | None = None,
        tier: Tier = "light",
        max_tokens: int = DEFAULT_MAX_TOKENS,
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
        request_log = self._build_log_payload(
            purpose=purpose,
            tier=tier,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            images=images,
            context=context,
            max_tokens=max_tokens,
        )

        try:
            if self.is_stub:
                raw = _stub_envelope(purpose, context or {})
                model = STUB_MODEL_NAME
                parsed = self._parse_and_validate(raw, response_schema)
            else:
                raw, parsed = await self._call_api(
                    purpose=purpose,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=response_schema,
                    images=images,
                    tier=tier,
                    max_tokens=max_tokens,
                )
                model = str(raw.get("model") or self.router_name(tier))
        except AIServiceError as exc:
            self._record(
                recorder,
                purpose=purpose,
                related_type=related_type,
                related_id=related_id,
                model=None,
                request_payload=request_log,
                response_payload=exc.details.get("response"),
                latency_ms=_elapsed_ms(started),
                is_stub=self.is_stub,
                error=exc.message,
            )
            raise

        latency_ms = _elapsed_ms(started)
        self._record(
            recorder,
            purpose=purpose,
            related_type=related_type,
            related_id=related_id,
            model=model,
            request_payload=request_log,
            response_payload=raw,
            latency_ms=latency_ms,
            is_stub=self.is_stub,
            error=None,
        )
        return OrcaResult(
            parsed=parsed, raw=raw, model=model, latency_ms=latency_ms, is_stub=self.is_stub
        )

    # ------------------------------------------------------------------
    # 実呼び出し
    # ------------------------------------------------------------------
    async def _call_api(
        self,
        *,
        purpose: Purpose,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        images: list[ImageInput] | None,
        tier: Tier,
        max_tokens: int,
    ) -> tuple[dict[str, Any], BaseModel]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _user_content(user_prompt, images)},
        ]
        attempts = self._settings.orca_max_retries + 1
        last_error = "AIの呼び出しに失敗しました。"
        budget = max_tokens

        for attempt in range(attempts):
            body = {
                "model": self.router_name(tier),
                "messages": messages,
                "temperature": TEMPERATURE,
                "max_tokens": budget,
            }
            try:
                response = await self._http().post(CHAT_COMPLETIONS_PATH, json=body)
            except httpx.TimeoutException as exc:
                last_error = f"AIの呼び出しがタイムアウトしました: {exc}"
                if not await self._sleep_before_retry(attempt, attempts, reason="timeout"):
                    raise AIServiceError(last_error) from exc
                continue
            except httpx.HTTPError as exc:
                last_error = f"AIサービスへの通信に失敗しました: {exc}"
                if not await self._sleep_before_retry(attempt, attempts, reason="http_error"):
                    raise AIServiceError(last_error) from exc
                continue

            if self._is_retryable_status(
                response, purpose=purpose, has_images=bool(images), tier=tier
            ):
                last_error = f"AIの呼び出しに失敗しました（HTTP {response.status_code}）。"
                if not await self._sleep_before_retry(
                    attempt,
                    attempts,
                    reason=f"http_{response.status_code}",
                    retry_after=_retry_after_seconds(response),
                ):
                    raise AIServiceError(last_error, details={"status": response.status_code})
                continue

            raw = response.json()
            try:
                parsed = self._parse_and_validate(raw, response_schema)
            except AIServiceError as exc:
                truncated = _finish_reason_of(raw) == "length"
                last_error = (
                    "AIの応答が max_tokens に達して本文が返りませんでした。"
                    if truncated
                    else exc.message
                )
                logger.warning(
                    "AI応答のJSON解析に失敗しました",
                    extra={
                        "purpose": purpose,
                        "attempt": attempt + 1,
                        "truncated": truncated,
                        "max_tokens": budget,
                        "reason": exc.message,
                    },
                )
                if attempt + 1 >= attempts:
                    raise AIServiceError(last_error, details={"response": raw}) from exc

                if truncated:
                    # 推論トークンで上限を使い切っている。形式の指摘ではなく予算を増やす
                    budget = min(MAX_TOKENS_CEILING, budget * 2)
                    continue

                # 直前の出力を見せて、JSONのみを出すよう指示して再試行する（1.1節の4段階目）
                messages = [
                    *messages,
                    {"role": "assistant", "content": _content_of(raw) or ""},
                    {"role": "user", "content": _JSON_REPAIR_MESSAGE},
                ]
                continue

            return raw, parsed

        raise AIServiceError(last_error)

    def _is_retryable_status(
        self, response: httpx.Response, *, purpose: Purpose, has_images: bool, tier: Tier
    ) -> bool:
        """リトライすべきステータスなら True。リトライ不可なら例外を送出する（1.1節の表）。"""
        status = response.status_code
        if status < 300:
            return False

        if status in (401, 403):
            logger.error(
                "OrcaRouter の認証に失敗しました。ORCA_API_KEY の設定を確認してください",
                extra={"status": status, "purpose": purpose},
            )
            raise AIServiceError(
                "AIサービスの認証に失敗しました。APIキーの設定を確認してください。",
                details={"status": status},
            )

        if status == 400:
            # 画像付きで 400 のときは Vision 非対応モデルへ振られた可能性がある。
            # リトライでは解決しないため、環境変数の見直しを促して止める（1.1節）。
            if has_images:
                logger.error(
                    "画像付きリクエストが 400 で拒否されました。"
                    "Vision対応モデルのみを許可したルーターを ORCA_ROUTER_VISION に設定してください",
                    extra={"router": self.router_name(tier), "purpose": purpose},
                )
                raise AIServiceError(
                    "画像を扱えるモデルへルーティングされませんでした。"
                    "ORCA_ROUTER_VISION に Vision対応のルーターを設定してください。",
                    details={"status": status, "body": response.text[:500]},
                )
            logger.error(
                "OrcaRouter がリクエストを拒否しました",
                extra={"status": status, "purpose": purpose, "body": response.text[:500]},
            )
            raise AIServiceError("AIへのリクエストが拒否されました。", details={"status": status})

        if status == 429 or status >= 500:
            return True

        raise AIServiceError(
            f"AIの呼び出しに失敗しました（HTTP {status}）。", details={"status": status}
        )

    async def _sleep_before_retry(
        self, attempt: int, attempts: int, *, reason: str, retry_after: float | None = None
    ) -> bool:
        if attempt + 1 >= attempts:
            return False
        delay = (
            retry_after
            if retry_after is not None
            else BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
        )
        logger.warning(
            "AI呼び出しをリトライします",
            extra={"reason": reason, "attempt": attempt + 1, "delay_seconds": delay},
        )
        await asyncio.sleep(delay)
        return True

    def _parse_and_validate(
        self, raw: dict[str, Any], response_schema: type[BaseModel]
    ) -> BaseModel:
        content = _content_of(raw)
        if content is None:
            raise AIServiceError("AIの応答が空でした。")
        try:
            payload = extract_json_object(content)
        except ValueError as exc:
            raise AIServiceError(f"AIの応答をJSONとして解析できませんでした: {exc}") from exc
        try:
            return response_schema.model_validate(payload)
        except ValidationError as exc:
            raise AIServiceError(
                f"AIの応答がスキーマに一致しませんでした（{exc.error_count()}件）。"
            ) from exc

    # ------------------------------------------------------------------
    def _build_log_payload(
        self,
        *,
        purpose: Purpose,
        tier: Tier,
        system_prompt: str,
        user_prompt: str,
        images: list[ImageInput] | None,
        context: dict[str, Any] | None,
        max_tokens: int,
    ) -> dict[str, Any]:
        return {
            "purpose": purpose,
            "tier": tier,
            "model": self.router_name(tier),
            "temperature": TEMPERATURE,
            "maxTokens": max_tokens,
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

    # ------------------------------------------------------------------
    # 画像生成（投稿サムネイル）
    # ------------------------------------------------------------------
    @property
    def image_generation_enabled(self) -> bool:
        """画像生成が使えるか。

        ルーター名（`ORCA_ROUTER_IMAGE`）が未設定、またはスタブモードでは使えない。
        使えない場合、呼び出し側はストリートビュー画像などへフォールバックする。
        """
        return bool(self._settings.orca_router_image) and not self.is_stub

    async def generate_image(
        self,
        *,
        prompt: str,
        size: int,
        recorder: InvocationRecorder | None = None,
        related_type: str | None = None,
        related_id: uuid.UUID | None = None,
    ) -> GeneratedImage:
        """テキストから画像を生成する（OpenAI images 互換のエンドポイントを想定）。

        TODO(human-decision): OrcaRouter の画像生成APIの正式な形式が未確認。
        判明したらこのメソッドの内部だけを差し替える（呼び出し側は変更不要）。
        """
        if not self.image_generation_enabled:
            raise AIServiceError("画像生成が有効ではありません（ORCA_ROUTER_IMAGE が未設定です）。")

        router = self._settings.orca_router_image
        payload: dict[str, Any] = {
            "model": router,
            "prompt": prompt,
            "size": f"{size}x{size}",
            "n": 1,
            "response_format": "b64_json",
        }
        started = time.perf_counter()
        try:
            response = await self._http().post(self._settings.orca_images_path, json=payload)
        except httpx.HTTPError as exc:
            self._record(
                recorder,
                purpose="thumbnail_generation",
                related_type=related_type,
                related_id=related_id,
                model=router,
                request_payload={"prompt": prompt, "size": size},
                response_payload=None,
                latency_ms=_elapsed_ms(started),
                is_stub=False,
                error=str(exc),
            )
            raise AIServiceError("画像生成の呼び出しに失敗しました。") from exc

        latency_ms = _elapsed_ms(started)
        if response.status_code >= 300:
            self._record(
                recorder,
                purpose="thumbnail_generation",
                related_type=related_type,
                related_id=related_id,
                model=router,
                request_payload={"prompt": prompt, "size": size},
                response_payload=None,
                latency_ms=latency_ms,
                is_stub=False,
                error=f"status={response.status_code} body={response.text[:300]}",
            )
            raise AIServiceError("画像生成に失敗しました。")

        body = response.json()
        image_bytes = await self._extract_image(body)
        self._record(
            recorder,
            purpose="thumbnail_generation",
            related_type=related_type,
            related_id=related_id,
            model=body.get("model") or router,
            request_payload={"prompt": prompt, "size": size},
            # 画像そのものはログへ残さない（サイズが大きいため）
            response_payload={"bytes": len(image_bytes)},
            latency_ms=latency_ms,
            is_stub=False,
            error=None,
        )
        return GeneratedImage(
            data=image_bytes, model=body.get("model") or router, latency_ms=latency_ms
        )

    async def _extract_image(self, body: dict[str, Any]) -> bytes:
        """`b64_json` と `url` のどちらの形式でも画像バイト列を取り出す。"""
        items = body.get("data") or []
        if not isinstance(items, list) or not items:
            raise AIServiceError("画像生成の応答に画像が含まれていません。")
        first = items[0] if isinstance(items[0], dict) else {}

        encoded = first.get("b64_json")
        if isinstance(encoded, str) and encoded:
            try:
                return base64.b64decode(encoded)
            except (ValueError, TypeError) as exc:
                raise AIServiceError("画像生成の応答を復号できませんでした。") from exc

        url = first.get("url")
        if isinstance(url, str) and url:
            try:
                downloaded = await self._http().get(url)
                downloaded.raise_for_status()
            except httpx.HTTPError as exc:
                raise AIServiceError("生成された画像を取得できませんでした。") from exc
            return downloaded.content

        raise AIServiceError("画像生成の応答形式が想定と異なります。")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ----------------------------------------------------------------------
# ヘルパー
# ----------------------------------------------------------------------
def _user_content(user_prompt: str, images: list[ImageInput] | None) -> Any:
    """画像がなければ文字列、あれば OpenAI Vision 形式の配列を返す。"""
    if not images:
        return user_prompt
    content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    for image in images:
        content.append({"type": "image_url", "image_url": {"url": image.to_data_uri()}})
    return content


def _content_of(raw: dict[str, Any]) -> str | None:
    choices = raw.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    return content if isinstance(content, str) else None


def _finish_reason_of(raw: dict[str, Any]) -> str | None:
    choices = raw.get("choices") or []
    return choices[0].get("finish_reason") if choices else None


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def extract_json_object(text: str) -> dict[str, Any]:
    """コードフェンスや前置きの文章が付いていても JSON を取り出す（1.1節の2〜3段階目）。"""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        loaded = json.loads(cleaned)
    except json.JSONDecodeError:
        loaded = None
    if isinstance(loaded, dict):
        return loaded

    start = cleaned.find("{")
    if start == -1:
        raise ValueError("JSONオブジェクトが見つかりません")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = json.loads(cleaned[start : index + 1])
                if not isinstance(candidate, dict):
                    raise ValueError("JSONオブジェクトではありません")
                return candidate
    raise ValueError("JSONオブジェクトが閉じていません")


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _stub_envelope(purpose: Purpose, context: dict[str, Any]) -> dict[str, Any]:
    """スタブ応答を実呼び出しと同じエンベロープに包み、解析経路を共通化する。"""
    content = _stub_content(purpose, context)
    return {
        "id": "stub",
        "model": STUB_MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(content, ensure_ascii=False),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _stub_daylight_state(captured_hour: object) -> str:
    """申告された撮影時刻（日本時間の「時」）から、もっともらしい光の状態を返す。

    スタブは画像を見ていないため、ここを固定値にすると夜間の撮影で「daylight」を
    返してしまい、C-5の環境整合チェックが不整合と判定してしまう。
    """
    if not isinstance(captured_hour, int):
        return "unknown"
    if 7 <= captured_hour < 16:
        return "daylight"
    if 16 <= captured_hour < 19 or 5 <= captured_hour < 7:
        return "twilight"
    return "night"


def _stub_content(purpose: Purpose, context: dict[str, Any]) -> dict[str, Any]:
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

    if purpose == "task_description_generation":
        title = str(context.get("title") or "指定された対象")
        return {
            "description": f"{title}について、対象の全体と現在の状態が分かるように正面から撮影してください。"
        }

    if purpose == "image_validation":
        # マスキングの座標問い合わせは同じ purpose を使うため、stage で分岐する
        if context.get("stage") == "masking":
            return {"regions": []}

        # 再撮影ループを見せるため、奇数回目の提出はわざと不合格にする。
        # 不合格の理由に「暗すぎます」を使うと、夜間の撮影で毎回それが出ることになり、
        # 画像を見ていないことが露骨に分かってしまう。**時間帯に依存しない理由**を使う。
        attempt_no = int(context.get("attempt_no", 1))
        daylight = _stub_daylight_state(context.get("captured_hour"))
        if attempt_no % 2 == 1:
            return {
                "score": 45,
                "subject_present": True,
                "framing_ok": False,
                "sharpness_ok": True,
                "brightness_ok": True,
                "reference_match": None,
                "observed_scene": "街路と建設中の建物（対象が画面の端に寄っている）",
                "daylight_state": daylight,
                "weather_hint": "cloudy",
                "issues": [
                    {
                        "code": "ANGLE_MISMATCH",
                        "message": "対象が端に寄っています。中央に収めて撮り直してください",
                    }
                ],
                "summary": "対象は写っていますが、画角から一部が外れています。",
            }
        return {
            "score": 88,
            "subject_present": True,
            "framing_ok": True,
            "sharpness_ok": True,
            "brightness_ok": True,
            "reference_match": None,
            "observed_scene": "街路と建設中の建物",
            "daylight_state": daylight,
            "weather_hint": "clear",
            "issues": [],
            "summary": "工事は予定通り進行中。安全対策は適切に実施されています。",
        }

    if purpose == "environment_check":
        return {"consistent": True, "note": "画像内の光の状態は撮影時刻と矛盾しない"}

    if purpose == "result_summary":
        # 画像は見られないが、依頼の題目と検品時の所見は分かる。
        # 固定文を返すとどの依頼でも同じ総括になってしまうため、材料をつないで返す。
        title = str(context.get("title") or "依頼")
        observations = context.get("observations")
        if isinstance(observations, list) and observations:
            detail = "。".join(str(item).rstrip("。") for item in observations[:2])
            return {"summary": f"「{title}」について撮影を確認しました。{detail}。"}
        return {"summary": f"「{title}」について、現地の状況を撮影した画像を確認しました。"}

    return {"summary": "現地の状況を撮影した画像を確認しました。"}


@lru_cache
def get_orca_client() -> OrcaClient:
    return OrcaClient()
