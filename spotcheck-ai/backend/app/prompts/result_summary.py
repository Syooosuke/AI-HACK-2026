"""クライアント向け調査結果総括のプロンプト。"""

from app.models import Task

SYSTEM_PROMPT = """あなたは現地調査結果をクライアント向けに要約するAIです。
依頼内容と提出画像を照合し、画像から確認できる事実だけを日本語で簡潔にまとめてください。
予定どおり、安全である、問題がない、など画像だけでは断定できない内容を推測してはいけません。
説明やMarkdownを含めず、次のJSONオブジェクトだけを返してください。
{"summary": "調査結果の要約（120文字以内）"}"""


def build_user_prompt(task: Task, observations: list[str]) -> str:
    observed = "\n".join(f"- {item}" for item in observations if item) or "（個別所見なし）"
    return f"""【依頼タイトル】{task.title}
【依頼内容】{task.description}
【撮影地点】{task.location_address or f'{task.location_lat}, {task.location_lng}'}
【画像検品時の個別所見】
{observed}

添付された安全処理済み画像を確認し、依頼に対する調査結果をJSONで返してください。"""
