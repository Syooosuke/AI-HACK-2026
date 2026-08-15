# 01. アーキテクチャ

## 1. 全体構成

```
[ブラウザ]
  ├─ クライアント側UI (Next.js)
  └─ ワーカー側UI (Next.js / PWA・カメラ利用)
        │  JSON / multipart over HTTPS
        ▼
[FastAPI バックエンド :8000]
  ├─ API層 (app/api/routes/)
  ├─ サービス層 (app/services/)
  │    ├─ task_review.py     … 依頼審査（LLM）
  │    ├─ image_validation.py… 画像検品（VLM）
  │    ├─ location_check.py  … 位置・時刻整合
  │    ├─ masking.py         … YOLO＋ぼかし
  │    └─ orca_client.py     … OrcaRouter 通信の唯一の窓口
  ├─ リポジトリ層 (app/repositories/)
  └─ バックグラウンドジョブ (app/jobs/)
        │
        ├──▶ [Supabase PostgreSQL]  … 業務データ
        ├──▶ [Supabase Storage]     … 画像（原本 / 加工後）
        └──▶ [OrcaRouter]           … LLM / VLM 推論
```

**設計原則**

- フロントエンドはDBに直接アクセスしない。すべてFastAPI経由とする（Supabaseクライアントはフロントに入れない）。
- 画像原本（マスキング前）は**クライアントに絶対に返さない**。Storage上でバケットを分離する。
- AIの呼び出しはすべて `OrcaClient` に集約する。モデル名やルーティング条件を業務ロジックに散らさない。

---

## 2. ディレクトリ構成

```
spotcheck-ai/
├── CLAUDE.md
├── docs/
├── docker-compose.yml            # ローカル用（任意）
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── main.py               # FastAPIアプリ、CORS、例外ハンドラ、ルーター登録
│   │   ├── core/
│   │   │   ├── config.py         # pydantic-settings による環境変数読み込み
│   │   │   ├── db.py             # SQLAlchemy Engine / Session
│   │   │   ├── storage.py        # Supabase Storage アップロード/署名URL発行
│   │   │   ├── security.py       # パスワードハッシュ化とJWTの発行・検証
│   │   │   ├── exceptions.py     # 独自例外
│   │   │   └── logging.py        # 構造化ログ
│   │   ├── models/               # SQLAlchemy モデル
│   │   │   ├── user.py
│   │   │   ├── task.py
│   │   │   ├── task_assignment.py
│   │   │   ├── submission.py
│   │   │   ├── payment.py
│   │   │   └── ai_invocation.py
│   │   ├── schemas/              # Pydantic スキーマ（リクエスト/レスポンス）
│   │   ├── repositories/
│   │   ├── services/
│   │   │   ├── orca_client.py
│   │   │   ├── task_review.py
│   │   │   ├── image_validation.py
│   │   │   ├── location_check.py
│   │   │   ├── masking.py
│   │   │   ├── submission_pipeline.py   # 検品パイプラインの統括
│   │   │   └── payment_stub.py
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── routes/
│   │   │       ├── tasks.py
│   │   │       ├── submissions.py
│   │   │       ├── users.py
│   │   │       └── health.py
│   │   ├── jobs/
│   │   │   └── expire_tasks.py   # 期限超過タスクのクローズ
│   │   └── prompts/              # プロンプトテンプレート（.jinja または .py 定数）
│   │       ├── task_review.py
│   │       └── image_validation.py
│   ├── models_weights/           # YOLO重み（.gitignore対象）
│   ├── scripts/
│   │   └── seed_demo_users.py
│   └── tests/
└── frontend/
    ├── package.json
    ├── .env.local.example
    ├── tailwind.config.ts
    └── src/
        ├── app/
        │   ├── layout.tsx
        │   ├── page.tsx                       # ロール選択（デモ用エントリ）
        │   ├── client/
        │   │   ├── tasks/new/page.tsx         # ①依頼作成
        │   │   ├── tasks/new/review/page.tsx  # ②AI審査結果
        │   │   ├── tasks/page.tsx             # 依頼一覧
        │   │   └── tasks/[taskId]/
        │   │       ├── page.tsx               # ③依頼公開・進行状況
        │   │       ├── results/page.tsx       # ⑨結果閲覧
        │   │       └── results/[submissionId]/page.tsx  # ⑩結果詳細
        │   └── worker/
        │       ├── tasks/page.tsx             # ④依頼一覧/地図
        │       └── tasks/[taskId]/
        │           ├── page.tsx               # ⑤依頼詳細・受注
        │           ├── capture/page.tsx       # ⑥撮影・アップロード
        │           └── status/page.tsx        # ⑦⑧検品結果・再撮影指示
        ├── components/
        │   ├── ui/                            # Button, Card, Badge, Stepper 等
        │   ├── map/                           # LocationPicker, TaskMarkers, PlaceSearchBox
        │   ├── task/                          # TaskCard, StatusTimeline, ScorePanel
        │   └── capture/                       # CameraView, MetadataOverlay
        ├── lib/
        │   ├── api/                           # auth.ts, tasks.ts, submissions.ts, client.ts
        │   ├── geo.ts                         # 距離計算・座標フォーマット
        │   └── session.ts                     # トークンとユーザー情報の保持
        └── types/
            └── api.ts                         # バックエンドのスキーマに対応する型
```

---

## 3. 環境変数

### backend/.env.example

```bash
# --- アプリ ---
APP_ENV=development
API_PORT=8000
CORS_ORIGINS=http://localhost:3000

# --- データベース ---
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/spotcheck

# --- 認証（ログインID＋パスワード / JWT）---
JWT_SECRET=                    # 未設定なら開発用の固定鍵。本番相当の環境では必ず設定する
#JWT_EXPIRE_DAYS=30            # ログイン状態を保持する日数
#BCRYPT_ROUNDS=12              # パスワードハッシュのコスト

# --- Supabase（Dashboard → Settings → API Keys）---
SUPABASE_URL=
SUPABASE_SECRET_KEY=           # sb_secret_...（サーバー専用。フロントへ渡さない）
#SUPABASE_SERVICE_ROLE_KEY=    # 旧方式のJWT。2026年末廃止予定。上が未設定のときのみ使用
STORAGE_BUCKET_RAW=submissions-raw        # 原本（非公開・クライアントに渡さない）
STORAGE_BUCKET_PROCESSED=submissions-processed  # マスキング済み（非公開・署名URLで配信）
STORAGE_BACKEND=auto           # auto / supabase / local（autoはSupabase未設定時にlocalへフォールバック）
LOCAL_STORAGE_DIR=./.storage   # local バックエンド時の保存先

# --- OrcaRouter（API仕様は docs/04-ai-pipeline.md 1.1 で確定）---
ORCA_API_BASE_URL=https://api.orcarouter.ai/v1
ORCA_API_KEY=
# model に渡すのは「ルーター名」。モデル名をコードへ直書きしない
# orcarouter/auto は振り先が毎回変わるため使わない（docs/04-ai-pipeline.md 1.1「ルーター構成」）
ORCA_ROUTER_LIGHT=openai/gpt-5.4-mini                  # 意図判定・高速処理用
ORCA_ROUTER_VISION=qwen/qwen3-vl-235b-a22b-instruct    # 画像解析・高度判定用
ORCA_TIMEOUT_SECONDS=60
ORCA_MAX_RETRIES=2
ORCA_STUB_MODE=false           # true、またはORCA_API_KEY未設定でスタブ応答

# --- 判定パラメータ（チューニング可能な初期値）---
TASK_REVIEW_SCORE_THRESHOLD=70      # 依頼情報の十分性スコア。これ未満は補足要求
SUBMISSION_SCORE_THRESHOLD=60       # 画像検品スコア。これ未満は再撮影要求
MAX_RETAKE_COUNT=2                  # 再撮影の上限回数（提出は最大3回）
LOCATION_TOLERANCE_METERS=100       # 依頼地点と撮影地点の許容距離
TIMESTAMP_TOLERANCE_SECONDS=300     # 端末時刻とサーバー受信時刻の許容差
CAPTURE_FRESHNESS_SECONDS=600       # 撮影から送信までの許容経過時間

# --- 物体検出 ---
YOLO_MODEL_PATH=./models_weights/yolov8n.pt
YOLO_FACE_MODEL_PATH=./models_weights/yolov8n-face.pt
YOLO_CONFIDENCE_THRESHOLD=0.35
BLUR_KERNEL_RATIO=0.15              # 対象領域の短辺に対するぼかし強度比

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

### 閾値の設定根拠

| 変数 | 初期値 | 根拠 |
|---|---|---|
| `TASK_REVIEW_SCORE_THRESHOLD` | 70 | 「撮影対象・場所・条件」の3要素が揃えば70点以上になるようプロンプト側で採点基準を固定する |
| `SUBMISSION_SCORE_THRESHOLD` | 60 | 主要被写体が写っており、状態が読み取れれば70点以上が出る。構図・明るさの粗さで数点落ちても合格を残す |
| `LOCATION_TOLERANCE_METERS` | 100 | 都市部のGPS誤差（10〜50m）と撮影位置の自由度を考慮 |
| `TIMESTAMP_TOLERANCE_SECONDS` | 300 | 端末時刻ズレの実用上限 |

**これらは環境変数で調整可能にすること。コード内にハードコードしない。**

---

## 4. 外部サービスの前提

| サービス | 用途 | 未取得時のフォールバック |
|---|---|---|
| Supabase | DB・画像ストレージ | ローカルPostgreSQL＋ローカルファイル保存に切替可能な `StorageBackend` 抽象を用意する |
| OrcaRouter | LLM/VLM推論 | `ORCA_API_KEY` 未設定時は固定レスポンスを返すスタブモードで動作させ、画面フローの確認を可能にする |
| Google Maps API | 地図表示・ピン指定 | キー未設定時は緯度経度の手入力フォームにフォールバック |

**スタブモードは必須要件である。** デモ当日にAPI障害が起きても画面が通るよう、`ORCA_STUB_MODE=true` で全AI呼び出しを固定レスポンスに切り替えられるようにする。