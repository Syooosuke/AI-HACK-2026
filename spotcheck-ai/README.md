# SpotCheck AI

遠隔地の現況確認（不動産管理・広告監査・工事進捗確認など）を依頼したいクライアントと、
現地にいるワーカーをマッチングするプラットフォーム。

**人間による目視検品を一切排除**し、以下をAIが一貫して自動処理する。

1. 依頼テキストの意図解析（犯罪目的・撮影禁止場所のブロック）
2. 依頼情報の十分性スコアリング（不足なら補足を要求）
3. 提出画像のVLM検品（条件を満たすかの判定と再撮影指示）
4. 位置偽装（Spoofing）検知
5. 顔・ナンバープレート・表札の自動マスキング

仕様は `CLAUDE.md` と `docs/` にある。実装はそちらを正とする。

---

## 構成

| ディレクトリ | 内容 |
|---|---|
| `backend/` | FastAPI（Python 3.11+）。API・AI連携・検品パイプライン |
| `frontend/` | Next.js 14（App Router / TypeScript / Tailwind）。画面①〜⑩ |
| `docs/` | 設計ドキュメント（アーキテクチャ・DB・API・AI・画面・フェーズ） |
| `docker-compose.yml` | ローカル開発用の PostgreSQL（任意） |

---

## セットアップ

### 1. データベース

```bash
docker compose up -d db          # localhost:5432 に PostgreSQL が起動する
```

Supabase の PostgreSQL を使う場合はこの手順は不要。`DATABASE_URL` を差し替える。

### 2. バックエンド

```bash
cd backend
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
cp .env.example .env             # 値を埋める（未設定でも起動はする）
./.venv/bin/alembic upgrade head
./.venv/bin/python -m scripts.seed_demo_users
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

`GET http://localhost:8000/api/health` が 200 を返せば起動できている。
不足している環境変数は起動ログに警告として出る。

### 3. フロントエンド

```bash
cd frontend
npm install
cp .env.local.example .env.local # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev                      # http://localhost:3000
```

### 4. 環境変数

| 変数 | 未設定時の挙動 |
|---|---|
| `DATABASE_URL` | 既定のローカル接続（docker-compose の PostgreSQL）を使う |
| `SUPABASE_URL` / `SUPABASE_SECRET_KEY` | 画像をローカルディレクトリへ保存する（`LOCAL_STORAGE_DIR`） |
| `ORCA_API_KEY` | AIをスタブモードで動かす（固定応答。デモは通る） |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | 地図の代わりに緯度経度の手入力フォームを出す |

Supabase を使う場合は、初回のみバケットを作成する。

```bash
cd backend && ./.venv/bin/python -m scripts.init_storage
```

`submissions-raw`（原本）と `submissions-processed`（マスキング済み）を**非公開**で作成する。
原本はクライアントに一切返さない。

### 5. マスキング用の重み（任意）

顔・車両検出はローカル推論。重みが無い場合はマスキングをスキップして警告を出す。

```bash
cd backend/models_weights
curl -sLO https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
curl -sL -o yolov8n-face.pt https://huggingface.co/arnabdhar/YOLOv8-Face-Detection/resolve/main/model.pt
```

---

## 開発コマンド

```bash
# バックエンド
cd backend && ./.venv/bin/pytest              # テスト
cd backend && ./.venv/bin/ruff check .        # Lint
cd backend && ./.venv/bin/alembic revision --autogenerate -m "message"

# フロントエンド
cd frontend && npm run lint
cd frontend && npx tsc --noEmit
cd frontend && npm run build
```

テストは `spotcheck_test` データベースを自動作成し、マイグレーションを適用して実行する。
ストレージはローカル、AIはスタブへ固定されるため、外部サービスへは接続しない。

### スタブモード

`ORCA_STUB_MODE=true`（または `ORCA_API_KEY` 未設定）で、AIを固定応答に切り替える。

| 用途 | スタブの応答 |
|---|---|
| 依頼審査 | `approved` / スコア85 |
| 画像検品 | 奇数回目は45点で不合格（`TOO_DARK`）、偶数回目は88点で合格 |

画像検品を交互に失敗させるのは、**デモで再撮影ループを見せるため**。
デモ当日の障害対策としてこのモードは維持する。

---

## デモシナリオ

`http://localhost:3000` を開き、トップでユーザーを選ぶ。

1. **デモ株式会社**（クライアント）で「駅前の再開発工事の進捗確認」を作成
   → AI審査でスコアが出て公開される
2. 参考に「隣の家に人がいるか確認してほしい」を作成
   → **AIが却下する**（安全性のアピール）
3. 情報不足の依頼（「写真撮ってきて」だけ）を作成
   → **AIが補足要求を出す** → その場で補足して再審査 → 公開
4. ヘッダー右上から **山田 太郎**（ワーカー）へ切替 → 地図/リストで依頼を発見 → 受注
5. カメラで撮影（GPS取得済バッジとタイムスタンプが出ている状態）→ 提出
6. **1回目は不合格 → 再撮影指示が具体的に表示される** → 再撮影して合格
7. **顔とナンバープレートがマスクされた画像**が生成される
8. クライアントに切替 → 結果画面で AI要約・Reality Score・ワーカー評価を確認

> 画面⑥のカメラは HTTPS が必要（`localhost` は例外）。スマートフォンで試す場合は
> `npx next dev --experimental-https` かトンネル経由で開く。
> カメラが使えない環境ではファイル選択にフォールバックする。

---

## 実装状況

| Phase | 内容 | 状態 |
|---|---|---|
| 0 | 環境構築 | 完了 |
| 1 | DB＋CRUD API（AIはスタブ） | 完了 |
| 2 | 画面①〜⑩の一気通貫 | 完了 |
| 3 | 依頼審査AI | 完了 |
| 4 | 画像検品AI＋位置偽装対策 | 完了 |
| 5 | プライバシー自動マスキング | 完了 |
| 6 | 仕上げ（期限ジョブ・決済スタブ・エラー処理） | 完了 |

未検証のまま残っている点は `docs/06-phases.md` と各フェーズのコミットメッセージに記載。

- スマートフォン実機（HTTPS）でのカメラ・GPS動作
- Google Maps API キーを設定した状態での地図描画
