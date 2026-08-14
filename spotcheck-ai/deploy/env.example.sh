# deploy/env.sh の雛形。コピーして値を入れる（deploy/env.sh は .gitignore 済み）。
#
#   cp deploy/env.example.sh deploy/env.sh

# --- Google Cloud ---
PROJECT_ID=""                      # gcloud projects list で確認できるID
REGION="asia-northeast1"           # 東京
BACKEND_SERVICE="spotcheck-backend"
FRONTEND_SERVICE="spotcheck-frontend"
# デモ中はコールドスタート（YOLO込みで数十秒）を避けるため 1 にしてもよい。課金は増える
BACKEND_MIN_INSTANCES="0"
FRONTEND_MIN_INSTANCES="0"

# --- DB（Supabase の PostgreSQL）---
# Supabase Dashboard → Project Settings → Database → Connection string → URI
# 取得した文字列の postgresql:// を postgresql+psycopg:// に置き換える
# 例: postgresql+psycopg://postgres.xxxx:PASSWORD@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres
DATABASE_URL=""

# --- 認証 ---
# 生成例: python3 -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET=""

# --- Supabase Storage（backend/.env と同じ値）---
SUPABASE_URL=""
SUPABASE_SECRET_KEY=""

# --- AI（OrcaRouter）---
ORCA_API_KEY=""
ORCA_STUB_MODE="false"             # true にすると固定応答になり、マスキングと検品が実質無効になる
ORCA_ROUTER_IMAGE=""               # サムネイルのAI画像生成に使うルーター名（未設定なら生成しない）

# --- 用途ごとのモデル（docs/04-ai-pipeline.md 1.2）---
# 「間違えたときの損失」で割り当てを変える。実写真での比較結果は
#   backend/scripts/bench_models.py で再現できる。
# orcarouter/auto は中身が予告なく変わるため、重要な用途では使わない。
ORCA_MODEL_TASK_REVIEW="anthropic/claude-opus-5"        # 犯罪目的の見落としは取り返しがつかない
ORCA_MODEL_IMAGE_VALIDATION="anthropic/claude-opus-5"   # 中核。実測5/5・最速だった
ORCA_MODEL_MASKING="anthropic/claude-opus-5"            # 顔・ナンバーの取りこぼしは法的問題になる
ORCA_MODEL_RESULT_SUMMARY="anthropic/claude-opus-5"     # クライアントが読む文章
ORCA_MODEL_TASK_DESCRIPTION="openai/gpt-5-mini"         # 利用者が待つので速さ優先。後から編集できる
ORCA_MODEL_THUMBNAIL="qwen/qwen3.5-flash"               # 表示上の飾り。失敗しても影響しない

# --- 冗長化 ---
# 同じ入力でもスコアが合否をまたいで振れるため、重要な判定は多数決で決める。
ORCA_REVIEW_JURY="google/gemini-3.1-pro-preview,openai/gpt-5-mini"     # 審査は常に3モデル
ORCA_VALIDATION_JURY="google/gemini-3.1-pro-preview,openai/gpt-5-mini" # 検品は境界のときだけ
ORCA_VALIDATION_BOUNDARY="15"      # |score - しきい値| がこの幅なら再判定

# --- 地図 ---
GOOGLE_MAPS_SERVER_API_KEY=""      # サーバー側のストリートビュー取得用
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY="" # ブラウザ側の地図・検索・ストリートビュー用
NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT="35.6595"
NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG="139.7005"

# --- CORS ---
# 初回はフロントのURLが未確定なので空でよい（デプロイ後に update-env-vars で設定する）
CORS_ORIGINS=""
