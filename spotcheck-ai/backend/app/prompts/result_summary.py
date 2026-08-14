"""クライアント向け調査結果総括のプロンプト。"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.models import Task

JST = ZoneInfo("Asia/Tokyo")

SYSTEM_PROMPT = """あなたは現地調査の結果を、依頼したクライアントへ報告するAIです。

**依頼者が知りたかったことに答えてください。** 画像の説明ではなく、依頼への回答を書きます。
たとえば「工事の進捗を知りたい」なら進捗の状態を、「看板が出ているか知りたい」なら
その有無を、最初に述べてください。

守ること:
- 画像から実際に確認できる事実だけを書く
- 「予定どおり」「安全である」「問題ない」など、画像だけでは断定できない評価を書かない
  （比較対象や基準が与えられていないため）
- 依頼内容に対して確認できなかった点がある場合は、その旨を正直に書く
- 一般論や推測で字数を埋めない。書けることが少なければ短くてよい

説明やMarkdownを含めず、次のJSONオブジェクトだけを返してください。
{"summary": "依頼への回答（120文字以内）"}"""


def build_user_prompt(task: Task, observations: list[str]) -> str:
    observed = "\n".join(f"- {item}" for item in observations if item) or "（個別所見なし）"
    return f"""【依頼者が知りたいこと（タイトル）】{task.title}
【依頼者からの指示（詳細メッセージ）】{task.description}
【撮影地点】{task.location_address or f"{task.location_lat}, {task.location_lng}"}
【依頼者が希望した撮影日時】{_jst(task.scheduled_at)}
【画像検品時の個別所見】
{observed}

添付された安全処理済み画像を確認し、**上記の「依頼者が知りたいこと」への回答**をJSONで返してください。
指示の中に具体的な確認項目がある場合は、その項目ごとに結果が分かるように書いてください。"""


def _jst(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(JST).strftime("%Y-%m-%d %H:%M（日本時間）")
