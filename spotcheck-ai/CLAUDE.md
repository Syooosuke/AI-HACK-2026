# CLAUDE.md — SpotCheck AI 実装ガイド

このファイルは Claude Code がリポジトリ全体を通して常に参照する最上位の指示書である。
詳細仕様は `docs/` 配下に分割されている。実装前に該当ドキュメントを必ず読むこと。

| ドキュメント | 内容 | 読むべきタイミング |
|---|---|---|
| `docs/01-architecture.md` | 構成・ディレクトリ・環境変数 | 初期化時、必ず最初に |
| `docs/02-database.md` | テーブル定義・ステータス遷移 | マイグレーション作成時 |
| `docs/03-api.md` | APIエンドポイント仕様 | バックエンド実装時 |
| `docs/04-ai-pipeline.md` | OrcaRouter連携・プロンプト・検品 | AI機能実装時 |
| `docs/05-frontend.md` | 画面①〜⑩の仕様 | フロントエンド実装時 |
| `docs/06-phases.md` | 実装フェーズと完了条件 | 作業開始時・各フェーズ終了時 |

---

## 1. プロダクト概要

**SpotCheck AI** は、遠隔地の現況確認（不動産管理、広告監査、工事進捗確認など）を依頼したいクライアントと、現地にいるワーカーをマッチングするプラットフォームである。

最大の特徴は **人間による目視検品を一切排除** し、以下をAIが一貫して自動処理する点にある。

1. 依頼テキストの意図解析（犯罪目的・撮影禁止場所のブロック）
2. 依頼情報の十分性スコアリング（不足なら補足を要求）
3. 提出画像のVLM検品（条件を満たすかの判定と再撮影指示）
4. 位置偽装（Spoofing）検知
5. 顔・ナンバープレート・表札の自動マスキング

---

## 2. 確定した設計判断（変更禁止 / 変更時は必ず人間に確認）

これらは開発者本人が明示的に選択した事項である。**実装上の都合で勝手に変更してはならない。**

| # | 項目 | 決定内容 |
|---|---|---|
| D-01 | バックエンド | **Python FastAPI を別建て**（Next.js の API Routes に統合しない） |
| D-02 | 撮影方法 | アプリ内カメラで撮影し、**画像・デバイス位置情報・撮影時刻を同一リクエストでサーバーへ送信**する。EXIFは補助的な検証材料として扱う |
| D-03 | 決済 | **UIのみ実装し、処理はスタブ**。外部決済SDKは導入しない。DBに記録だけ残す |
| D-04 | LLMルーティング | **外部 OrcaRouter の API を実際に呼び出す**（APIキーは環境変数で供給される） |
| D-05 | 受注人数 | **1依頼に対しクライアントが撮影人数 N を指定**し、N人まで受注可能 |
| D-06 | 認証 | **仮実装**。デモ用の固定ユーザーをシードし、ヘッダー `X-Demo-User-Id` でユーザーを切り替える |
| D-07 | 検品・報酬の単位 | **ワーカー単位**。合格した人から逐次納品・報酬確定する（全員の完了を待たない） |
| D-08 | 再撮影ループ | **上限2回**（＝1ワーカーあたり提出は最大3回）。超過したら当該ワーカーの受注をキャンセルし、枠を他ワーカーへ再開放する |
| D-09 | マスキング | **YOLO系の物体検出モデルをローカル導入**して実行する（クラウドVision APIは使わない） |
| D-10 | 実装順序 | **デモ優先**。画面フローを先に通し、AI機能を後から差し込む（`docs/06-phases.md` 参照） |

---

## 3. 人間に判断を仰ぐべきケース（重要）

以下に該当した場合は、**推測で実装を進めず作業を止めて質問すること。**

- 上記 D-01〜D-10 の決定と矛盾する実装をせざるを得ないと判断したとき
- OrcaRouter の実際のレスポンス形式が `docs/04-ai-pipeline.md` の想定と異なっていたとき
- 課金・個人情報・法令（撮影禁止場所、肖像権）の扱いに新たな判断が必要になったとき
- スキーマに破壊的変更（カラム削除、型変更）が必要になったとき
- 仕様書に記載のない画面・機能を追加したくなったとき

**未確定事項（実装開始時点で人間に確認が必要）:**

- [ ] OrcaRouter のエンドポイントURL・認証ヘッダー形式・リクエスト/レスポンススキーマ
  → 確認が取れるまでは `docs/04-ai-pipeline.md` の `OrcaClient` インターフェース定義に従って実装し、実際の形式が判明した時点で `orca_client.py` の内部実装のみ差し替える。**呼び出し側のコードは変更しなくて済む設計にすること。**

---

## 4. 技術スタック

| レイヤ | 採用技術 |
|---|---|
| フロントエンド | Next.js 14+ (App Router), TypeScript, Tailwind CSS |
| バックエンド | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic |
| DB / ストレージ | Supabase (PostgreSQL + Storage) |
| LLM/VLM | OrcaRouter 経由 |
| 物体検出 | Ultralytics YOLO (ローカル推論) |
| 画像処理 | Pillow / OpenCV |
| 地図 | Google Maps JavaScript API |

---

## 5. コーディング規約

### 全体
- コメント・UI文言・エラーメッセージは**日本語**で記述する。
- 変数名・関数名・テーブル名・カラム名は**英語（snake_case / camelCase）**。
- 秘密情報をコードに直書きしない。必ず環境変数経由で読む。
- `TODO` を残す場合は `# TODO(human-decision): 内容` の形式にし、人間の判断が必要な旨を明示する。

### バックエンド
- 型ヒントを必ず付ける。Pydantic モデルでリクエスト/レスポンスを定義する。
- ルーター層はHTTPの入出力のみを担い、ビジネスロジックは `app/services/` に置く。
- DBアクセスは `app/repositories/` に集約し、サービス層から呼ぶ。
- AI呼び出しは必ず `OrcaClient` を経由する。OpenAI/Anthropic のSDKを直接 import しない。
- 例外は `app/core/exceptions.py` の独自例外に変換し、ハンドラで統一的にJSON化する。
- 重い処理（画像検品・マスキング）は FastAPI の `BackgroundTasks` で非同期実行し、APIは即座に `202 Accepted` を返す。

### フロントエンド
- Server Component をデフォルトとし、状態を持つ画面のみ `"use client"` を付ける。
- API呼び出しは `src/lib/api/` のクライアント関数に集約し、コンポーネントから `fetch` を直接書かない。
- 色・余白は Tailwind のデザイントークン（`docs/05-frontend.md` の定義）に従う。クライアント側は青系、ワーカー側は緑系で区別する。

---

## 6. Git / PR の運用ルール（違反したら作業を止める）

**このセクションのルールは例外を認めない。** 判断に迷ったら人間に確認する。

### 6.1 ブランチとPRの向き先

| 項目 | ルール |
|---|---|
| 分岐元 | **必ず `dev` から切る**（`main` や他の作業ブランチから切らない） |
| PRの向き先 | **`dev` のみ**。`base` が `dev` 以外のPRは**作らない／作られていたら棄却する** |
| `main` への直push | **禁止** |
| `main` へのPR | **禁止**（`dev` → `main` の同期も勝手に行わない） |
| ブランチ名 | `feat/` `fix/` `docs/` `chore/` などの接頭辞＋内容（例: `fix/files-missing-image-404`） |

```bash
# 正しい始め方
git checkout dev && git pull --ff-only origin dev
git checkout -b fix/対象-内容

# PR は base を明示して dev へ
gh pr create --base dev --head <branch>
```

`main` を `dev` に揃える必要が出た場合は、**実行前に人間へ確認する**。

### 6.2 push / PR の前に必ず通すもの

**壊れた状態を共有しないため、以下がすべて通ってから push / PR する。**
1件でも失敗したら push せず、原因を直す。

```bash
cd backend  && ./.venv/bin/ruff check . && ./.venv/bin/ruff format --check . && ./.venv/bin/pytest -q
cd frontend && npx tsc --noEmit && npm run lint
```

- `pytest` は `spotcheck_test` DB を自動作成するため **`docker compose up -d db` が必要**
- テストを飛ばしたい場合でも、**飛ばした事実を必ず報告する**（黙って飛ばさない）
- 既存テストを「通らないから」といって削除・スキップしてはならない。
  仕様変更で期待値が変わった場合のみ、変更理由をコミットメッセージに書いて更新する

これらは `.githooks/pre-push` でも機械的に検査している（6.4参照）。

### 6.3 マージ後の後片付け

PRがマージされたら、**リモートとローカルの状態を一致させる**。

```bash
gh pr merge <番号> --merge --delete-branch      # リモートのブランチも削除する
git checkout dev && git pull --ff-only origin dev
git branch -d <branch>                          # ローカルも削除
git fetch --prune origin                        # 消えたリモート追跡を掃除
```

マージ済みのブランチを残さない。`git branch -a` に merged 済みのものが残っていたら掃除する。

### 6.4 機械的な強制

| 仕組み | 何を防ぐか |
|---|---|
| `.githooks/pre-push` | `main` への push、`dev` 由来でないブランチの push、lint / テスト未通過での push |
| GitHub の ruleset（`main`） | 直push・force push・ブランチ削除。PRを介さない変更 |

フックは各自の環境で一度だけ有効化する（クローン直後に実行）。

```bash
git config core.hooksPath .githooks
```

緊急時に限り `SPOTCHECK_SKIP_CHECKS=1 git push` で検査を飛ばせるが、
**使ったら必ず理由を報告する。**

---

## 7. 作業の進め方

1. `docs/06-phases.md` のフェーズ順に実装する。フェーズを飛ばさない。
2. 各フェーズの完了条件をすべて満たしてから次へ進む。
3. 1フェーズ完了ごとにコミットする。コミットメッセージは `feat(phase-N): 概要` の形式。
4. フェーズ完了時に、動作確認手順と未解決事項を報告する。

### コマンド

```bash
# バックエンド
cd backend && uvicorn app.main:app --reload --port 8000
cd backend && alembic revision --autogenerate -m "message"
cd backend && alembic upgrade head
cd backend && pytest

# フロントエンド
cd frontend && npm run dev     # http://localhost:3000
cd frontend && npm run lint
cd frontend && npm run build
```