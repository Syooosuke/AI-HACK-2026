"""ai_invocations テーブルへのアクセス（AI呼び出しの監査ログ）。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AiInvocation


def create(
    session: Session,
    *,
    purpose: str,
    related_type: str | None = None,
    related_id: uuid.UUID | None = None,
    model: str | None = None,
    request_payload: dict[str, Any] | None = None,
    response_payload: dict[str, Any] | None = None,
    latency_ms: int | None = None,
    is_stub: bool = False,
    error: str | None = None,
) -> AiInvocation:
    """1回のAI呼び出しを記録する。画像のbase64は呼び出し側で除去済みであること。"""
    invocation = AiInvocation(
        purpose=purpose,
        related_type=related_type,
        related_id=related_id,
        model=model,
        request_payload=request_payload,
        response_payload=response_payload,
        latency_ms=latency_ms,
        is_stub=is_stub,
        error=error,
    )
    session.add(invocation)
    session.flush()
    return invocation
