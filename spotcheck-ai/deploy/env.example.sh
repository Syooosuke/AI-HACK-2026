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

# tier の既定。**orcarouter/auto を使わない。** 振り先が毎回変わり、推論モデルへ当たると
# reasoning tokens で max_tokens を使い切って本文が空で返る（実測で依頼文生成が 1/8 しか成功しなかった）。
ORCA_ROUTER_LIGHT="openai/gpt-5.4-mini"
ORCA_ROUTER_VISION="qwen/qwen3-vl-235b-a22b-instruct"  # Vision非対応へ振られる事故も防ぐ

# --- 用途ごとのモデル（docs/04-ai-pipeline.md 1.2）---
# 「間違えたときの損失」で割り当てを変える。比較は backend/scripts/ の2本で再現できる。
#   bench_task_review.py … 依頼審査（正当な依頼を却下していないか）
#   bench_models.py       … 画像検品（合否と被写体が模範解答どおりか）
ORCA_MODEL_TASK_REVIEW="anthropic/claude-opus-5"        # 犯罪目的の見落としは取り返しがつかない
ORCA_MODEL_IMAGE_VALIDATION="anthropic/claude-opus-5"   # 中核。実測5/5、合格側の余裕が+18で最大
ORCA_MODEL_MASKING="anthropic/claude-opus-5"            # 顔・ナンバーの取りこぼしは法的問題になる
ORCA_MODEL_RESULT_SUMMARY="anthropic/claude-opus-5"     # クライアントが読む文章
ORCA_MODEL_TASK_DESCRIPTION="openai/gpt-5.4-mini"       # gpt-5-mini は推論に予算を使い切り 0/4 だった
ORCA_MODEL_THUMBNAIL="qwen/qwen3.5-flash"               # 表示上の飾り。失敗しても影響しない

# --- 冗長化 ---
# 同じ入力でもスコアが合否をまたいで振れるため、重要な判定は多数決で決める。
# **2モデルにしない。** 票が割れると必ず慎重側（rejected）になり、
# 却下は書き直して再申請できない行き止まりのため、誤却下がそのまま失注になる。
ORCA_REVIEW_JURY="anthropic/claude-haiku-4.5,openai/gpt-5.4-mini"       # 審査は常に3モデル（実測5.8秒）
ORCA_VALIDATION_JURY="qwen/qwen3-vl-235b-a22b-instruct,openai/gpt-5.4-mini" # 検品は境界のときだけ
ORCA_VALIDATION_BOUNDARY="15"      # |score - しきい値| がこの幅なら再判定

# --- 地図 ---
GOOGLE_MAPS_SERVER_API_KEY=""      # サーバー側のストリートビュー取得用
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY="" # ブラウザ側の地図・検索・ストリートビュー用
NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT="35.6595"
NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG="139.7005"

# --- CORS ---
# 初回はフロントのURLが未確定なので空でよい（デプロイ後に update-env-vars で設定する）
CORS_ORIGINS=""
