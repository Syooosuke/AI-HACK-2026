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

## APIキーの扱い（最初に読んでください）

**APIキーはリポジトリで共有しません。各自が自分のキーを用意するか、キー無しで動かします。**

- `backend/.env` と `frontend/.env.local` は **`.gitignore` 済み**。コミットされません
- リポジトリに入っているのは**値が空の雛形**（`.env.example` / `.env.local.example`）だけです
- **キーが1つも無くても、全画面が動きます。** AIは固定応答（スタブ）、画像はローカル保存、
  地図は緯度経度の手入力にフォールバックします。まずはこの状態で立ち上げてください

| ファイル | Git | 中身 | 用意する人 |
|---|---|---|---|
| `backend/.env.example` | ✅ コミット | 雛形（値は空） | — |
| `backend/.env` | ❌ 無視 | 実際の値 | 各自 |
| `frontend/.env.local.example` | ✅ コミット | 雛形（値は空） | — |
| `frontend/.env.local` | ❌ 無視 | 実際の値 | 各自 |

> `git add -f` を使わない限り `.env` が誤ってコミットされることはありません。
> 念のため `git status --porcelain` の出力に `.env` が現れないことを確認してから push してください。

---

## セットアップ（キー無しで動かす / 所要5分）

### 1. データベース

```bash
cd spotcheck-ai
docker compose up -d db          # localhost:5432 に PostgreSQL が起動する
```

Mac を再起動したら再度実行してください（自動起動しません）。

### 2. バックエンド

```bash
cd backend
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
cp .env.example .env             # そのままでOK。値は埋めなくても起動する
./.venv/bin/alembic upgrade head
./.venv/bin/python -m scripts.seed_demo_users
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

`GET http://localhost:8000/api/health` が 200 を返せば起動できています。
不足している環境変数は起動ログに警告として出ます（**警告が出ていても動きます**）。

### 3. フロントエンド

別のターミナルで:

```bash
cd frontend
npm install
cp .env.local.example .env.local # そのままでOK
npm run dev                      # http://localhost:3000
```

### 4. 起動確認

```bash
docker ps --filter name=spotcheck-db --format '{{.Names}} {{.Status}}'
curl -s -o /dev/null -w "backend  %{http_code}\n" http://localhost:8000/api/health
curl -s -o /dev/null -w "frontend %{http_code}\n" http://localhost:3000/
```

`healthy` / `200` / `200` なら完了です。`http://localhost:3000` を開くとログイン画面が出ます。

### 5. ログイン

`scripts.seed_demo_users` で投入されるアカウントを使います（パスワードは全員 `spotcheck123`）。

| ログインID | 表示名 |
|---|---|
| `demo_company` | デモ株式会社 |
| `yamada` | 山田 太郎 |
| `sato` | 佐藤 花子 |
| `suzuki` | 鈴木 一郎 |

画面右上の「新規登録」から自分のアカウントを作ることもできます。
**ロールはありません**。どのアカウントでも「依頼する」と「撮影する」の両方ができます
（ただし自分が出した依頼は自分で受注できません。動作確認には2アカウント使ってください）。

パスワードを変えたい場合は `DEMO_USER_PASSWORD=好きなパスワード ./.venv/bin/python -m scripts.seed_demo_users`。

---

## 追加設定（各自のキーを入れて機能を有効化する）

どれも**任意**です。入れなくてもデモは通ります。

| 入れる変数 | 有効になるもの | 未設定時の挙動 |
|---|---|---|
| `ORCA_API_KEY`（backend） | 実際のAI審査・画像検品 | 固定応答のスタブ（デモは通る） |
| `SUPABASE_URL` + `SUPABASE_SECRET_KEY`（backend） | Supabase Storage への画像保存 | ローカル保存（`LOCAL_STORAGE_DIR`） |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`（frontend） | 地図表示・場所検索・住所の自動取得 | 緯度経度の手入力フォーム |
| `JWT_SECRET`（backend） | 本番相当のトークン署名 | 開発用の固定鍵（誰でも偽造できる） |
| `DATABASE_URL`（backend） | 別のDBを使う | docker-compose のローカルDB |

### AI（OrcaRouter）

`backend/.env` の `ORCA_API_KEY` に自分のキーを設定し、`ORCA_STUB_MODE=false` にします。
`.py` を1つ触るか uvicorn を再起動すると反映されます（**`.env` の変更は自動反映されません**）。

> 実測レイテンシは依頼審査 20〜90秒、画像検品 30秒〜15分です。画面⑦のポーリングは
> 仕様どおり60秒で打ち切るため、**デモを通す場合は `ORCA_STUB_MODE=true` を推奨**します。

### Supabase Storage

`SUPABASE_URL` と `SUPABASE_SECRET_KEY`（Dashboard → Settings → API Keys の `sb_secret_...`）を
設定し、初回のみバケットを作成します。

```bash
cd backend && ./.venv/bin/python -m scripts.init_storage
```

`submissions-raw`（原本）と `submissions-processed`（マスキング済み）を**非公開**で作成します。
原本はクライアントに一切返しません。`SUPABASE_SECRET_KEY` は**サーバー専用**で、
`NEXT_PUBLIC_` を付けたりフロントに置いたりしないでください。

### Google Maps

**最短（課金設定なし）**: [Maps Demo Key](https://developers.google.com/maps/documentation/javascript/demo-key)
で「Get a Demo Key」を押すとその場でキーが出ます。プロトタイピング専用・日次クォータあり。

**通常**: [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作り、
請求先アカウントを紐付けて次の2つを有効化 → 「認証情報」でAPIキーを作成。

- **Maps JavaScript API**（地図本体）
- **Geocoding API**（ピンを置いた時の住所自動取得と、地名・住所のテキスト検索）
- **Places API**（任意。検索ボックスの候補表示。無効でも Geocoding によるテキスト検索で動きます）

取得したキーを `frontend/.env.local` の `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` に設定します。
`next dev` が `.env.local` を自動リロードするので、ブラウザを Cmd+Shift+R で再読み込みしてください。

> `NEXT_PUBLIC_` の値は**ブラウザに露出します**。キーの編集画面で必ず制限してください。
> アプリケーションの制限 → HTTPリファラー `http://localhost:3000/*` /
> APIの制限 → `Maps JavaScript API` / `Geocoding API`（＋使う場合は `Places API`）のみ。

うまく表示されないときはブラウザのコンソール（F12）にGoogleのエラー名が出ます。

| エラー | 原因 |
|---|---|
| `InvalidKeyMapError` | キー文字列の誤り（前後の空白・改行） |
| `ApiNotActivatedMapError` | Maps JavaScript API が未有効 |
| `BillingNotEnabledMapError` | 請求先アカウント未設定（→ Demo Key を使う） |
| `RefererNotAllowedMapError` | リファラー制限に `http://localhost:3000/*` が無い |

キーが不正でもアプリは落ちず、手入力フォームへ自動フォールバックします。

### マスキング用の重み

顔・車両検出はローカル推論です。重みが無い場合はマスキングをスキップして警告を出します
（画像は配信されます）。

```bash
cd backend/models_weights
curl -sLO https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
curl -sL -o yolov8n-face.pt https://huggingface.co/arnabdhar/YOLOv8-Face-Detection/resolve/main/model.pt
```

`yolov8n-face.pt` は公式配布ではありません（第三者のHugging Faceリポジトリ）。
ライセンスを確認のうえ利用してください。重みは `.gitignore` 済みでコミットされません。

---

## `git pull` した後にやること

| 変わっていたら | 実行するコマンド |
|---|---|
| `backend/pyproject.toml` | `cd backend && ./.venv/bin/pip install -e ".[dev]"` |
| `backend/alembic/versions/` にファイル追加 | `cd backend && ./.venv/bin/alembic upgrade head` |
| `frontend/package.json` | `cd frontend && npm install` |
| `.py` / `.tsx` のみ | 何もしなくてよい（`--reload` / `next dev` が自動反映） |

迷ったら次を実行しても壊れません（すべて冪等）。

```bash
(cd backend && ./.venv/bin/pip install -q -e ".[dev]" && ./.venv/bin/alembic upgrade head && ./.venv/bin/pytest -q)
(cd frontend && npm install && npx tsc --noEmit)
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
