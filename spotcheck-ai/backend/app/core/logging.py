"""構造化ログの設定。

`key=value` 形式でコンテキストを付与できる薄い実装にする。外部ログ基盤は導入しない。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

_CONFIGURED = False

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class KeyValueFormatter(logging.Formatter):
    """`logger.info("msg", extra={...})` の extra を key=value で末尾に付ける。"""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED and not key.startswith("_")
        }
        if not extras:
            return base
        rendered = " ".join(f"{key}={_render(value)}" for key, value in extras.items())
        return f"{base} {rendered}"


def _render(value: Any) -> str:
    text = str(value)
    return f'"{text}"' if " " in text else text


def setup_logging(level: int = logging.INFO) -> None:
    """アプリ起動時に一度だけ呼ぶ。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        KeyValueFormatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn のロガーもルートへ委譲させ、フォーマットを統一する
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
