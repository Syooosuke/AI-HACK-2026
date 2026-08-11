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
ORCA_STUB_MODE="true"              # デモを安定させるなら true
ORCA_ROUTER_IMAGE=""               # サムネイルのAI画像生成に使うルーター名（未設定なら生成しない）

# --- 地図 ---
GOOGLE_MAPS_SERVER_API_KEY=""      # サーバー側のストリートビュー取得用
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY="" # ブラウザ側の地図・検索・ストリートビュー用
NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT="35.6595"
NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG="139.7005"

# --- CORS ---
# 初回はフロントのURLが未確定なので空でよい（デプロイ後に update-env-vars で設定する）
CORS_ORIGINS=""
