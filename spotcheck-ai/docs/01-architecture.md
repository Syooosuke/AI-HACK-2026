# 01. アーキテクチャ

このドキュメントは**現在のコードの状態**を記述する。設計上の意図は `CLAUDE.md` の D-01〜D-10 を参照する。

---

## 1. 全体構成

```
[ブラウザ / スマートフォン]
  └─ Next.js 14 (App Router)  … ログイン後は全ユーザー同じ画面構成
        │  JSON / multipart over HTTPS
        │  Authorization: Bearer <JWT>
        ▼
[FastAPI バックエンド :8000]
  ├─ API層 (app/api/routes/)   … auth / users / tasks / submissions / social / notifications / files / health
  ├─ サービス層 (app/services/)
  │    ├─ orca_client.py        … OrcaRouter 通信の唯一の窓口
  │    ├─ content_filter.py     … AIより先に通す決定論フィルタ（機能A前段）
  │    ├─ task_review.py        … 依頼審査（機能A・合議あり）
  │    ├─ image_validation.py   … 画像検品（機能B・境界再判定あり）
  │    ├─ location_check.py     … 位置・時刻整合／Reality Score（機能C）
  │    ├─ masking.py            … YOLO＋VLM座標＋ぼかし／黒塗り（機能D）
  │    ├─ thumbnail_service.py  … 投稿サムネイル生成（機能E）
  │    ├─ result_summary.py     … クライアント向け総括
  │    └─ submission_pipeline.py… 検品パイプラインの統括
  ├─ リポジトリ層 (app/repositories/)
  └─ バックグラウンド
       ├─ FastAPI BackgroundTasks … 検品パイプライン・サムネイル生成
       └─ APScheduler (5分間隔)   … app/jobs/expire_tasks.py
        │
        ├──▶ [PostgreSQL]        … Supabase、またはローカル docker compose
        ├──▶ [Supabase Storage]  … 画像（原本 / 加工後）。未設定ならローカルファイル
        ├──▶ [OrcaRouter]        … LLM / VLM 推論
        └──▶ [Google Maps]       … Street View Static API（サーバー側キー）
```

**設計原則**

- フロントエンドはDBに直接アクセスしない。すべてFastAPI経由（Supabaseクライアントはフロントに入れない）。
- 画像原本（マスキング前）は**クライアントに絶対に返さない**。Storage上でバケットを分離する。
- AIの呼び出しはすべて `OrcaClient` に集約する。モデル名やルーティング条件を業務ロジックに散らさない。
- 認証は JWT のみ。**ロールは持たない**（D-06）。権限は依頼のオーナーか受注者かで判定する。

---

## 2. ディレクトリ構成（現状）

```
AI-HACK-2026/
├── .github/workflows/deploy.yml       # main への push で Cloud Run へ自動デプロイ
└── spotcheck-ai/
    ├── CLAUDE.md
    ├── docker-compose.yml             # ローカル用 PostgreSQL（db サービスのみ）
    ├── docs/
    │   ├── 01-architecture.md 〜 07-deployment.md
    │   ├── competitor-research.md     # 競合調査
    │   ├── zenn-article.md            # 技術記事の下書き
    │   └── assets/demo-qr.png
    ├── deploy/
    │   ├── deploy.sh                  # 手動デプロイ（障害時の退避手段）
    │   ├── env.example.sh / env.sh    # env.sh は .gitignore 済み
    │   ├── make_qr.py                 # デモ用QRコード生成
    │   └── set_db_url.py
    ├── backend/
    │   ├── pyproject.toml             # ruff / pytest の設定もここ
    │   ├── Dockerfile / .dockerignore
    │   ├── .env.example
    │   ├── alembic/versions/          # マイグレーション7本（2節 02-database.md）
    │   ├── models_weights/            # YOLO重み（.gitignore対象）
    │   ├── app/
    │   │   ├── main.py                # CORS・例外ハンドラ・ルーター登録・lifespan
    │   │   ├── core/
    │   │   │   ├── config.py          # pydantic-settings。全項目にデフォルト値を持つ
    │   │   │   ├── db.py              # Engine は遅延生成。prepare_threshold=None
    │   │   │   ├── storage.py         # Supabase / Local の StorageBackend 抽象
    │   │   │   ├── security.py        # bcrypt ハッシュと JWT の発行・検証
    │   │   │   ├── geo.py             # Haversine・バウンディングボックス
    │   │   │   ├── exceptions.py      # AppError 系
    │   │   │   └── logging.py         # key=value の構造化ログ
    │   │   ├── models/                # SQLAlchemy モデル（10テーブル）
    │   │   │   ├── user.py  task.py  task_assignment.py  submission.py
    │   │   │   ├── payment.py  ai_invocation.py  notification.py
    │   │   │   ├── task_like.py  saved_search.py  worker_review.py
    │   │   │   ├── enums.py  base.py
    │   │   ├── schemas/               # Pydantic（CamelModel 基底で camelCase 変換）
    │   │   ├── repositories/          # DBアクセスの集約
    │   │   ├── services/              # 業務ロジック（1節の一覧）
    │   │   ├── prompts/               # task_review / image_validation / masking /
    │   │   │                          #   result_summary / task_description / thumbnail
    │   │   ├── api/
    │   │   │   ├── deps.py            # DbSession / CurrentUser
    │   │   │   └── routes/            # auth files health notifications social
    │   │   │                          #   submissions tasks users
    │   │   └── jobs/expire_tasks.py
    │   ├── scripts/
    │   │   ├── seed_demo_users.py     # デモユーザー4名（固定UUID）
    │   │   ├── seed_demo_tasks.py     # 投稿カード確認用の依頼
    │   │   ├── seed_worker_review_demo.py
    │   │   ├── init_storage.py        # バケット作成
    │   │   ├── download_yolo_models.py
    │   │   ├── regenerate_thumbnails.py
    │   │   ├── bench_models.py        # 画像検品のモデル比較（課金あり）
    │   │   └── bench_task_review.py   # 依頼審査のモデル比較（課金あり）
    │   └── tests/                     # pytest。spotcheck_test DB を自動作成する
    └── frontend/
        ├── package.json / next.config.mjs / tailwind.config.ts
        ├── Dockerfile / cloudbuild.yaml   # NEXT_PUBLIC_* を build-arg で埋め込む
        ├── .env.local.example
        └── src/
            ├── app/
            │   ├── layout.tsx  page.tsx            # / はログイン状態で振り分け
            │   ├── login/  signup/
            │   ├── home/                           # ホーム（近くの依頼）
            │   ├── search/                         # 地図でさがす
            │   ├── likes/                          # いいね＋保存した検索条件
            │   ├── notifications/                  # お知らせ
            │   ├── me/                             # マイページ
            │   ├── users/[userId]/                 # 公開プロフィール（画面⑪）
            │   ├── requests/                       # 依頼する側
            │   │   ├── new/  new/review/           # 画面①②
            │   │   ├── page.tsx                    # 依頼一覧
            │   │   └── [taskId]/  [taskId]/results/[submissionId]/   # 画面③⑨⑩
            │   └── jobs/                           # 撮影する側
            │       ├── page.tsx                    # 受注一覧
            │       └── [taskId]/  capture/  status/ # 画面⑤⑥⑦⑧
            ├── components/
            │   ├── auth/AuthGuard.tsx
            │   ├── layout/AppShell.tsx  Logo.tsx
            │   ├── ui/    # Avatar Stars StatusBadge Toast TrustGauge index(Card等)
            │   ├── map/   # LocationPicker PlaceSearchBox StreetViewPanel
            │   │           # TaskMarkers useGoogleMaps
            │   ├── task/  # TaskCard CornerBadge IssueList PollingIndicator
            │   │           # PresetChips ScorePanel StatusTimeline TimeWindow
            │   └── capture/CameraView.tsx  MetadataOverlay.tsx
            ├── lib/
            │   ├── api/   # client auth tasks submissions social notifications
            │   │           # users errorMessages
            │   ├── datetime.ts  geo.ts  env.ts  session.ts
            │   ├── polling.ts        # 段階的バックオフ
            │   ├── pageCache.ts      # タブ移動時のちらつき防止
            │   ├── reviewHandoff.ts  # 画面①→②の受け渡し
            │   └── taskPresets.ts    # よくある依頼のひな形11件
            └── types/api.ts
```

---

## 3. 環境変数

### backend/.env.example（全項目）

`app/core/config.py` の `Settings` が唯一の読み取り口。**全項目にデフォルト値があるため `.env` が無くても起動する。**
不足分は起動時に `collect_config_warnings()` が警告としてログに出す（起動は止めない）。

```bash
# --- アプリ ---
APP_ENV=development                   # development / staging / production
API_PORT=8000
CORS_ORIGINS=http://localhost:3000    # カンマ区切り

# --- データベース ---
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/spotcheck

# --- 認証（D-06）---
JWT_SECRET=                    # 未設定なら開発用の固定鍵。production では未設定だと起動時に例外
#JWT_EXPIRE_DAYS=30
#BCRYPT_ROUNDS=12

# --- Supabase / ストレージ ---
SUPABASE_URL=
SUPABASE_SECRET_KEY=           # sb_secret_...（サーバー専用）
#SUPABASE_SERVICE_ROLE_KEY=    # 旧方式のJWT。上が未設定のときのみ使う
STORAGE_BUCKET_RAW=submissions-raw
STORAGE_BUCKET_PROCESSED=submissions-processed
STORAGE_BACKEND=auto           # auto / supabase / local
LOCAL_STORAGE_DIR=./.storage

# --- OrcaRouter（docs/04-ai-pipeline.md 1節）---
ORCA_API_BASE_URL=https://api.orcarouter.ai/v1
ORCA_API_KEY=
ORCA_ROUTER_LIGHT=openai/gpt-5.4-mini                # tier=light の既定
ORCA_ROUTER_VISION=qwen/qwen3-vl-235b-a22b-instruct  # tier=vision の既定
ORCA_TIMEOUT_SECONDS=60
ORCA_MAX_RETRIES=2
ORCA_STUB_MODE=false           # true、または ORCA_API_KEY 未設定でスタブ応答

# --- 用途ごとのモデル（未設定なら上の tier 既定へ落ちる）---
ORCA_MODEL_TASK_REVIEW=anthropic/claude-opus-5
ORCA_MODEL_IMAGE_VALIDATION=anthropic/claude-opus-5
ORCA_MODEL_MASKING=anthropic/claude-opus-5
ORCA_MODEL_RESULT_SUMMARY=anthropic/claude-opus-5
ORCA_MODEL_TASK_DESCRIPTION=openai/gpt-5.4-mini
ORCA_MODEL_THUMBNAIL=qwen/qwen3.5-flash

# --- 冗長化（多数決）---
ORCA_REVIEW_JURY=anthropic/claude-haiku-4.5,openai/gpt-5.4-mini   # 主モデル＋2 = 3票
ORCA_VALIDATION_JURY=qwen/qwen3-vl-235b-a22b-instruct,openai/gpt-5.4-mini
ORCA_VALIDATION_BOUNDARY=15    # |score − しきい値| ≤ この幅なら再判定

# --- 判定パラメータ ---
TASK_REVIEW_SCORE_THRESHOLD=70
SUBMISSION_SCORE_THRESHOLD=60
MAX_RETAKE_COUNT=2
LOCATION_TOLERANCE_METERS=100
TIMESTAMP_TOLERANCE_SECONDS=300
CAPTURE_FRESHNESS_SECONDS=600

# --- 投稿サムネイル（機能E）---
GOOGLE_MAPS_SERVER_API_KEY=    # Street View Static 用。フロントのキーとは分ける
#THUMBNAIL_SIZE=640
ORCA_ROUTER_IMAGE=             # 未設定ならストリートビュー画像をそのまま使う
#ORCA_IMAGES_PATH=/images/generations

# --- 投稿タグの判定 ---
#NEW_TASK_HOURS=24              # 作成からこの時間以内は NEW
#HOT_VIEW_COUNT=20              # 閲覧数がこの値以上で HOT

# --- 物体検出（D-09）---
YOLO_MODEL_PATH=./models_weights/yolov8n.pt
YOLO_FACE_MODEL_PATH=./models_weights/yolov8n-face.pt
YOLO_CONFIDENCE_THRESHOLD=0.35
BLUR_KERNEL_RATIO=0.15

# --- 画像制約 ---
MAX_UPLOAD_SIZE_MB=15
ALLOWED_IMAGE_TYPES=image/jpeg,image/png,image/webp
```

### frontend/.env.local.example

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=
NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT=35.6595
NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG=139.7005
```

`NEXT_PUBLIC_*` は**ビルド時にJSへ埋め込まれる**。値を変えたら再ビルドが必要（`docs/07-deployment.md` 4.0）。
参照は `src/lib/env.ts` に集約し、コンポーネントから `process.env` を直接読まない。

### 閾値の設定根拠

| 変数 | 現在値 | 根拠 |
|---|---|---|
| `TASK_REVIEW_SCORE_THRESHOLD` | 70 | 「撮影対象・場所・条件」の3要素が揃えば70点以上になるようプロンプト側で採点基準を固定している |
| `SUBMISSION_SCORE_THRESHOLD` | **60** | 対象が写り状態が読み取れれば70点以上が出る採点基準。構図・明るさの粗さで数点落ちても合格を残す（`docs/04-ai-pipeline.md` 3.2） |
| `LOCATION_TOLERANCE_METERS` | 100 | 都市部のGPS誤差（10〜50m）と撮影位置の自由度 |
| `TIMESTAMP_TOLERANCE_SECONDS` | 300 | 端末時刻ズレの実用上限 |
| `CAPTURE_FRESHNESS_SECONDS` | 600 | 撮り置き画像の投稿を防ぐ。API層で同期的に検証する |
| `ORCA_VALIDATION_BOUNDARY` | 15 | スコアの振れが観測されるのは境界付近だけ。全件を多重呼び出しにしない |

**これらは環境変数で調整可能にすること。コード内にハードコードしない。**

---

## 4. 外部サービスと未設定時の挙動

| サービス | 用途 | 未設定時のフォールバック |
|---|---|---|
| PostgreSQL | 業務データ | 既定の接続文字列がローカル `docker compose up -d db` を指す |
| Supabase Storage | 画像（原本 / 加工後） | `LocalStorageBackend` がローカルディレクトリへ保存し、`/api/files/{bucket}/{key}` で配信（**加工後バケットのみ許可**） |
| OrcaRouter | LLM / VLM 推論 | `ORCA_STUB_MODE=true` または `ORCA_API_KEY` 未設定でスタブ応答（HTTP通信なし） |
| Google Maps JS API | 地図・地点ピッカー・ストリートビュー | キー未設定・認証失敗（`window.gm_authFailure`）で緯度経度の手入力へ切替 |
| Street View Static API | サムネイル生成（機能E） | 未設定・パノラマ無しならサーバー描画のプレースホルダへ落とす |

**スタブモードは必須要件である。** デモ当日にAPI障害が起きても画面が通るよう、
`ORCA_STUB_MODE=true` で全AI呼び出しを固定レスポンスに切り替えられる状態を最後まで維持する。

> ただしスタブモードでは LLM 審査が丸ごと素通りするため、`content_filter.py` の
> 決定論フィルタが唯一の防波堤になる（`docs/04-ai-pipeline.md` 2.2.1）。

---

## 5. 起動と確認

```bash
# DB（Supabase を使わない場合）
docker compose up -d db

# バックエンド
cd backend && ./.venv/bin/alembic upgrade head
cd backend && ./.venv/bin/python -m scripts.seed_demo_users
cd backend && ./.venv/bin/uvicorn app.main:app --reload --port 8000

# フロントエンド
cd frontend && npm run dev      # http://localhost:3000
```

| 確認先 | 内容 |
|---|---|
| `GET /api/health` | 依存先の状態と `configWarnings`。不足があれば `status="degraded"` |
| `GET /api/health/db` | DBへの到達確認。接続不能でも 200 で詳細を返す |
| `GET /docs` | FastAPI の自動生成APIドキュメント |

push / PR の前に通すコマンドは `CLAUDE.md` 6.2 を参照する。
