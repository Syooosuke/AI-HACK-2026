"""投稿サムネイル生成のプロンプト。

ストリートビュー画像をVLMに読ませて現地の様子を短く言語化し、その説明と依頼内容から
画像生成用のプロンプトを組み立てる。**実在の看板・人物・車両ナンバーは書かせない。**
"""

from __future__ import annotations

from app.models import Task

SCENE_SYSTEM_PROMPT = """あなたは現地写真の代行撮影プラットフォームの画像編集アシスタントです。
与えられたストリートビュー画像を見て、撮影地点の様子を日本語で簡潔に説明してください。

制約:
- 建物の形・道路・空の広さ・時間帯の印象など、風景の構成に限って述べる。
- 実在の店名・看板の文字・人物の特徴・車両のナンバーには一切言及しない。
- 30〜80文字程度の1文にする。

必ず次のJSONだけを出力してください。
{"scene": "<説明>"}"""


def build_scene_user_prompt(task: Task) -> str:
    """ストリートビュー画像と一緒に渡すユーザープロンプト。"""
    place = task.location_address or f"{task.location_lat}, {task.location_lng}"
    return f"""【撮影地点】{place}
【依頼タイトル】{task.title}

この地点の風景を説明してください。"""


def build_image_prompt(task: Task, scene: str | None) -> str:
    """画像生成へ渡すプロンプト。

    実写と誤認されないよう、イラスト調であることを明示する。
    """
    place = task.location_address or f"{task.location_lat}, {task.location_lng}"
    described = scene or f"{place} 周辺の街並み"
    return (
        "日本の街並みを描いた、明るく落ち着いた色調のフラットイラスト。"
        f"次の風景を題材にしてください: {described}。"
        f"この絵は「{task.title}」という現地確認の依頼を表すサムネイルです。"
        "正方形の構図。文字・ロゴ・看板の文言・人物の顔・車両のナンバーは描かないこと。"
        "写真ではなくイラストとして描くこと。"
    )
