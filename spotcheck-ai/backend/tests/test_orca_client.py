"""OrcaClient の実HTTP呼び出しのテスト（docs/04-ai-pipeline.md 1節）。

実際の OrcaRouter を叩かず、httpx.MockTransport で応答を差し替えて検証する。
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from typing import Any

import httpx
import pytest
from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import AIServiceError
from app.schemas.ai import TaskReviewResult
from app.services import orca_client as orca_module
from app.services.orca_client import (
    MAX_IMAGE_LONG_EDGE,
    ImageInput,
    OrcaClient,
    encode_image_for_vlm,
    extract_json_object,
)

VALID_CONTENT = json.dumps(
    {
        "decision": "approved",
        "score": 85,
        "safety": "pass",
        "validity": "pass",
        "risk": "pass",
        "duplication": "pass",
        "rejection_reason": None,
        "missing_info": [],
        "summary": "駅前の工事の進捗を確認する依頼です。",
    },
    ensure_ascii=False,
)


def envelope(content: str, *, model: str = "grok/grok-4.5") -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


@pytest.fixture(autouse=True)
def live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """スタブモードを外し、実呼び出し経路を通す。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_stub_mode", False)
    monkeypatch.setattr(settings, "orca_api_key", "test-key")
    monkeypatch.setattr(settings, "orca_max_retries", 2)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """バックオフの待ち時間でテストを遅くしない。"""

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant)


def build_client(handler) -> tuple[OrcaClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request, len(requests))

    return OrcaClient(transport=httpx.MockTransport(wrapped)), requests


async def call(client: OrcaClient, **kwargs: Any):
    return await client.complete_json(
        purpose="task_review",
        system_prompt="system",
        user_prompt="user",
        response_schema=TaskReviewResult,
        **kwargs,
    )


# ----------------------------------------------------------------------
# 正常系
# ----------------------------------------------------------------------
async def test_successful_call_parses_and_reports_upstream_model() -> None:
    client, requests = build_client(
        lambda _r, _n: httpx.Response(200, json=envelope(VALID_CONTENT))
    )
    result = await call(client)

    assert isinstance(result.parsed, TaskReviewResult)
    assert result.parsed.score == 85
    # リクエストで送ったルーター名ではなく、応答の model（実際に使われたモデル）を入れる
    assert result.model == "grok/grok-4.5"
    assert result.is_stub is False
    assert result.raw["usage"]["total_tokens"] == 30

    body = json.loads(requests[0].content)
    assert body["model"] == get_settings().orca_router_light
    assert body["temperature"] == 0.2
    assert body["max_tokens"] == orca_module.DEFAULT_MAX_TOKENS
    assert body["messages"][0]["role"] == "system"
    # **1回目はスキーマを付けない**（docs/04-ai-pipeline.md 1.1）。
    # 常時付けると claude-opus-5 で約10倍（6秒→58〜78秒）遅くなる一方、判定は変わらなかった。
    # 解析に失敗したときだけ次の試行から強制する
    assert "response_format" not in body
    assert requests[0].url.path.endswith("/chat/completions")
    assert requests[0].headers["authorization"] == "Bearer test-key"


@pytest.mark.parametrize(
    "content",
    [
        f"```json\n{VALID_CONTENT}\n```",
        f"```\n{VALID_CONTENT}\n```",
        f"以下が審査結果です。\n{VALID_CONTENT}\nご確認ください。",
    ],
)
async def test_recovers_from_fences_and_prose(content: str) -> None:
    client, requests = build_client(lambda _r, _n: httpx.Response(200, json=envelope(content)))
    result = await call(client)
    assert result.parsed.score == 85  # type: ignore[union-attr]
    assert len(requests) == 1  # 再試行せずに救済できる


async def test_retries_with_repair_message_when_json_is_broken() -> None:
    def handler(_request: httpx.Request, attempt: int) -> httpx.Response:
        if attempt == 1:
            return httpx.Response(200, json=envelope("JSONではない返答です"))
        return httpx.Response(200, json=envelope(VALID_CONTENT))

    client, requests = build_client(handler)
    result = await call(client)

    assert result.parsed.score == 85  # type: ignore[union-attr]
    assert len(requests) == 2

    first = json.loads(requests[0].content)
    second = json.loads(requests[1].content)

    # 1回目はスキーマを付けない（速さのため）
    assert "response_format" not in first
    # 2回目のリクエストには修復指示が含まれる
    assert second["messages"][-1]["content"].startswith("直前の出力はJSONとして解析できませんでした")
    # **形が崩れた後はスキーマを強制する。** 遅くなるが、解析できないよりはよい
    assert second["response_format"]["type"] == "json_schema"
    assert second["response_format"]["json_schema"]["name"] == "TaskReviewResult"


async def test_schema_mismatch_finally_raises() -> None:
    broken = json.dumps({"decision": "approved"})  # 必須項目が足りない
    client, requests = build_client(lambda _r, _n: httpx.Response(200, json=envelope(broken)))

    with pytest.raises(AIServiceError) as exc:
        await call(client)
    assert "スキーマ" in exc.value.message
    assert len(requests) == 3  # ORCA_MAX_RETRIES=2 → 合計3回


# ----------------------------------------------------------------------
# エラー処理（docs/04-ai-pipeline.md 1.1 の表）
# ----------------------------------------------------------------------
async def test_401_does_not_retry() -> None:
    client, requests = build_client(
        lambda _r, _n: httpx.Response(401, json={"error": {"message": "Invalid token"}})
    )
    with pytest.raises(AIServiceError) as exc:
        await call(client)
    assert "認証" in exc.value.message
    assert exc.value.status_code == 502
    assert len(requests) == 1


async def test_400_does_not_retry() -> None:
    client, requests = build_client(lambda _r, _n: httpx.Response(400, text="bad request"))
    with pytest.raises(AIServiceError):
        await call(client)
    assert len(requests) == 1


async def test_429_is_retried_and_succeeds() -> None:
    def handler(_request: httpx.Request, attempt: int) -> httpx.Response:
        if attempt == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, text="rate limited")
        return httpx.Response(200, json=envelope(VALID_CONTENT))

    client, requests = build_client(handler)
    result = await call(client)
    assert result.parsed.score == 85  # type: ignore[union-attr]
    assert len(requests) == 2


async def test_server_error_exhausts_retries() -> None:
    client, requests = build_client(lambda _r, _n: httpx.Response(503, text="unavailable"))
    with pytest.raises(AIServiceError):
        await call(client)
    assert len(requests) == 3


async def test_timeout_is_retried() -> None:
    def handler(request: httpx.Request, attempt: int) -> httpx.Response:
        if attempt == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json=envelope(VALID_CONTENT))

    client, requests = build_client(handler)
    result = await call(client)
    assert result.parsed.score == 85  # type: ignore[union-attr]
    assert len(requests) == 2


# ----------------------------------------------------------------------
# 画像付き呼び出し
# ----------------------------------------------------------------------
def sample_image_bytes(size: tuple[int, int] = (3000, 2000)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_encode_image_resizes_long_edge() -> None:
    encoded = encode_image_for_vlm(sample_image_bytes())
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
        assert max(image.size) == MAX_IMAGE_LONG_EDGE
        assert image.format == "JPEG"


async def test_images_are_sent_as_base64_data_uri() -> None:
    client, requests = build_client(
        lambda _r, _n: httpx.Response(200, json=envelope(VALID_CONTENT))
    )
    encoded = encode_image_for_vlm(sample_image_bytes((100, 80)))
    await call(
        client,
        images=[ImageInput(url="task-reference/x/0.jpg", base64_data=encoded)],
        tier="vision",
    )

    body = json.loads(requests[0].content)
    assert body["model"] == get_settings().orca_router_vision
    content = body["messages"][1]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


async def test_400_with_images_points_at_vision_router() -> None:
    client, requests = build_client(
        lambda _r, _n: httpx.Response(400, text="model does not support images")
    )
    encoded = encode_image_for_vlm(sample_image_bytes((60, 60)))

    with pytest.raises(AIServiceError) as exc:
        await call(client, images=[ImageInput(base64_data=encoded)], tier="vision")
    assert "ORCA_ROUTER_VISION" in exc.value.message
    assert len(requests) == 1  # リトライしない


# ----------------------------------------------------------------------
# 監査ログとスタブモード
# ----------------------------------------------------------------------
async def test_recorder_receives_success_and_omits_base64() -> None:
    client, _requests = build_client(
        lambda _r, _n: httpx.Response(200, json=envelope(VALID_CONTENT))
    )
    records: list[dict[str, Any]] = []
    encoded = encode_image_for_vlm(sample_image_bytes((50, 50)))

    await call(
        client,
        images=[ImageInput(base64_data=encoded)],
        tier="vision",
        recorder=lambda **kwargs: records.append(kwargs),
    )

    assert len(records) == 1
    record = records[0]
    assert record["model"] == "grok/grok-4.5"
    assert record["error"] is None
    assert record["is_stub"] is False
    assert record["response_payload"]["usage"]["total_tokens"] == 30
    # base64 は保存しない
    assert record["request_payload"]["images"] == ["<image omitted>"]
    assert encoded not in json.dumps(record["request_payload"])


async def test_recorder_receives_error() -> None:
    client, _requests = build_client(lambda _r, _n: httpx.Response(401, text="nope"))
    records: list[dict[str, Any]] = []

    with pytest.raises(AIServiceError):
        await call(client, recorder=lambda **kwargs: records.append(kwargs))

    assert len(records) == 1
    assert records[0]["error"] is not None
    assert records[0]["model"] is None


async def test_stub_mode_does_not_touch_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "orca_stub_mode", True)

    def explode(_request: httpx.Request, _attempt: int) -> httpx.Response:
        raise AssertionError("スタブモードでHTTPを呼んではいけない")

    client, requests = build_client(explode)
    result = await call(client)

    assert result.is_stub is True
    assert result.model == "stub"
    assert result.parsed.score == 85  # type: ignore[union-attr]
    assert requests == []


# ----------------------------------------------------------------------
def test_extract_json_object_handles_nested_and_braces_in_strings() -> None:
    text = '前置き {"a": {"b": "}"}, "c": [1,2]} 後書き'
    assert extract_json_object(text) == {"a": {"b": "}"}, "c": [1, 2]}


def test_extract_json_object_rejects_non_object() -> None:
    with pytest.raises(ValueError):
        extract_json_object("ただの文章です")


async def test_truncated_response_retries_with_larger_budget() -> None:
    """finish_reason=length（推論トークンで本文が空）なら max_tokens を倍にして再試行する。"""

    def handler(_request: httpx.Request, attempt: int) -> httpx.Response:
        if attempt == 1:
            payload = envelope("")
            payload["choices"][0]["finish_reason"] = "length"
            return httpx.Response(200, json=payload)
        return httpx.Response(200, json=envelope(VALID_CONTENT))

    client, requests = build_client(handler)
    result = await call(client)

    assert result.parsed.score == 85  # type: ignore[union-attr]
    assert len(requests) == 2
    first = json.loads(requests[0].content)["max_tokens"]
    second = json.loads(requests[1].content)["max_tokens"]
    assert second == first * 2
    # 予算不足が原因なので、修復用の追加メッセージは送らない
    assert len(json.loads(requests[1].content)["messages"]) == 2


async def test_truncated_response_error_message_mentions_max_tokens() -> None:
    def handler(_request: httpx.Request, _attempt: int) -> httpx.Response:
        payload = envelope("")
        payload["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=payload)

    client, requests = build_client(handler)
    with pytest.raises(AIServiceError) as exc:
        await call(client)
    assert "max_tokens" in exc.value.message
    assert len(requests) == 3
    # 上限は MAX_TOKENS_CEILING で止まる
    budgets = [json.loads(request.content)["max_tokens"] for request in requests]
    assert budgets == [
        orca_module.DEFAULT_MAX_TOKENS,
        orca_module.DEFAULT_MAX_TOKENS * 2,
        min(orca_module.MAX_TOKENS_CEILING, orca_module.DEFAULT_MAX_TOKENS * 4),
    ]


def test_module_exposes_coordinate_max_tokens() -> None:
    # マスキング座標の問い合わせのみ 800（Phase 5 で使用）
    assert orca_module.COORDINATE_MAX_TOKENS == 800
