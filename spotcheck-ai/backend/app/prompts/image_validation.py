"""画像検品のプロンプト（docs/04-ai-pipeline.md 3.2, 3.3）。

文面は仕様のとおり。変更する場合は docs を先に更新すること。
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.models import Submission, Task

JST = ZoneInfo("Asia/Tokyo")

SYSTEM_PROMPT = """あなたは現地撮影代行プラットフォーム「SpotCheck AI」の画像検品AIです。
ワーカーが提出した画像が、クライアントの依頼条件を満たしているかを判定し、JSONのみを返してください。
説明文やマークダウンのコードフェンスは一切出力しないでください。

【採点基準 score（0〜100点）】
- 依頼された対象が明確に写っている: 40点
- 構図・画角が依頼条件に適合している: 20点
- ピントが合っている（被写体が判別可能）: 20点
- 明るさ・露出が適切で内容を確認できる: 20点
対象が全く写っていない場合、score は30点を超えてはいけません。

【issues】不合格要素がある場合、指定されたコードと、ワーカーが次に何をすべきかが分かる日本語の短い指示（30文字以内）を記述してください。合格なら空配列にしてください。
使用できるコードは次のみです: SUBJECT_MISSING / TOO_DARK / TOO_BLURRY / ANGLE_MISMATCH / TOO_FAR / OBSTRUCTED / OTHER

【observed_scene】画像に実際に写っているものを、依頼内容に引きずられず客観的に記述してください（60文字以内）。

【daylight_state】画像の光の状態から、昼・薄暮・夜・屋内のいずれかを判定してください。

【summary】クライアントが結果画面で読むための要約を、日本語60文字以内で記述してください。

判定は提出画像のみに基づいて行い、推測で「写っているはず」と判断しないでください。

【出力フォーマット】次のキーだけを持つJSONオブジェクトを出力してください。
{
  "score": 0〜100の整数,
  "subject_present": true | false,
  "framing_ok": true | false,
  "sharpness_ok": true | false,
  "brightness_ok": true | false,
  "reference_match": true | false | null,
  "observed_scene": 文字列,
  "daylight_state": "daylight" | "twilight" | "night" | "indoor" | "unknown",
  "weather_hint": "clear" | "cloudy" | "rain" | "snow" | "unknown",
  "issues": [{"code": コード, "message": 文字列}],
  "summary": 文字列
}"""

#: 参考画像がある場合の添付順（docs/04-ai-pipeline.md 3.3）
IMAGE_ORDER_WITH_REFERENCE = (
    "添付画像は1枚目がクライアントの参考画像、2枚目がワーカーの提出画像です。"
    "検品対象は2枚目の提出画像であり、1枚目は期待するイメージの参考として扱ってください。"
    "参考画像と一致していれば reference_match を true にしてください。"
)
IMAGE_ORDER_WITHOUT_REFERENCE = (
    "添付画像はワーカーの提出画像です。reference_match は null にしてください。"
)


def build_user_prompt(task: Task, submission: Submission, *, has_reference: bool) -> str:
    """docs/04-ai-pipeline.md 3.3 のテンプレート。"""
    return f"""【依頼内容】{task.description}
【撮影条件】{task.title}
【撮影地点の住所】{task.location_address or "（住所の登録なし）"}
【申告された撮影時刻】{_jst(submission.captured_at)}（日本時間）
【参考画像の有無】{"あり" if has_reference else "なし"}
【提出回数】{submission.attempt_no}回目

{IMAGE_ORDER_WITH_REFERENCE if has_reference else IMAGE_ORDER_WITHOUT_REFERENCE}

添付画像を検品し、JSONのみを出力してください。"""


def _jst(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(JST).strftime("%Y-%m-%d %H:%M")
