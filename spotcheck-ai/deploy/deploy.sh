#!/bin/bash
# SpotCheck AI を Google Cloud Run へデプロイする。
#
#   cd spotcheck-ai && ./deploy/deploy.sh            # バックエンド→フロントの順に両方
#   cd spotcheck-ai && ./deploy/deploy.sh backend    # バックエンドのみ
#   cd spotcheck-ai && ./deploy/deploy.sh frontend   # フロントのみ
#
# 前提:
# - gcloud にログイン済み（gcloud auth login）
# - deploy/env.sh に設定を書いてある（deploy/env.example.sh をコピーして作る）
# - DBは Supabase の PostgreSQL を使う（Cloud SQL は使わない）
#
# 環境変数は **YAMLファイル経由**で渡す。`--set-env-vars` は値に含まれる `@` `,` と
# 区切り文字が衝突して壊れるため（DATABASE_URL に `@` が入る）。
set -euo pipefail

cd "$(dirname "$0")/.."
TARGET="${1:-all}"

if [ ! -f deploy/env.sh ]; then
  echo "deploy/env.sh がありません。deploy/env.example.sh をコピーして値を入れてください。" >&2
  exit 1
fi
# set -a で読み込み、以降の python から環境変数として見えるようにする
set -a
# shellcheck disable=SC1091
source deploy/env.sh
set +a

: "${PROJECT_ID:?PROJECT_ID を deploy/env.sh に設定してください}"
: "${REGION:=asia-northeast1}"
: "${BACKEND_SERVICE:=spotcheck-backend}"
: "${FRONTEND_SERVICE:=spotcheck-frontend}"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "プロジェクト: $PROJECT_ID / リージョン: $REGION"
gcloud config set project "$PROJECT_ID" --quiet

# 指定したキーの環境変数を YAML（JSONはYAMLの部分集合）へ書き出す。空の値は含めない。
write_env_file() {
  local out="$1"
  shift
  python3 - "$out" "$@" <<'PY'
import json
import os
import sys

out, keys = sys.argv[1], sys.argv[2:]
values = {key: os.environ[key] for key in keys if os.environ.get(key)}
with open(out, "w", encoding="utf-8") as handle:
    json.dump(values, handle, ensure_ascii=False, indent=2)
print("  渡す環境変数:", ", ".join(values))
PY
}

deploy_backend() {
  : "${DATABASE_URL:?DATABASE_URL（Supabase の接続文字列）を設定してください}"
  : "${JWT_SECRET:?JWT_SECRET を設定してください}"
  export APP_ENV="${APP_ENV:-production}"

  local env_file="$WORK_DIR/backend-env.yaml"
  write_env_file "$env_file" \
    APP_ENV DATABASE_URL JWT_SECRET SUPABASE_URL SUPABASE_SECRET_KEY \
    ORCA_API_KEY ORCA_STUB_MODE ORCA_ROUTER_IMAGE GOOGLE_MAPS_SERVER_API_KEY CORS_ORIGINS

  echo "=== バックエンドをデプロイします（初回のビルドは10分前後）==="
  gcloud run deploy "$BACKEND_SERVICE" \
    --source backend \
    --quiet \
    --region "$REGION" \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 900 \
    --concurrency 20 \
    --min-instances "${BACKEND_MIN_INSTANCES:-0}" \
    --env-vars-file "$env_file"

  BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE" --region "$REGION" --format='value(status.url)')
  echo "バックエンド: $BACKEND_URL"
}

deploy_frontend() {
  BACKEND_URL="${BACKEND_URL:-$(gcloud run services describe "$BACKEND_SERVICE" --region "$REGION" --format='value(status.url)' 2>/dev/null || true)}"
  : "${BACKEND_URL:?バックエンドのURLが取得できません。先にバックエンドをデプロイしてください}"

  # NEXT_PUBLIC_* はビルド時に埋め込まれる
  export NEXT_PUBLIC_API_BASE_URL="$BACKEND_URL"
  export NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT="${NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT:-35.6595}"
  export NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG="${NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG:-139.7005}"

  local build_env_file="$WORK_DIR/frontend-build-env.yaml"
  write_env_file "$build_env_file" \
    NEXT_PUBLIC_API_BASE_URL NEXT_PUBLIC_GOOGLE_MAPS_API_KEY \
    NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG

  echo "=== フロントエンドをデプロイします（APIの向き先: ${BACKEND_URL}）==="
  gcloud run deploy "$FRONTEND_SERVICE" \
    --source frontend \
    --quiet \
    --region "$REGION" \
    --allow-unauthenticated \
    --memory 1Gi \
    --min-instances "${FRONTEND_MIN_INSTANCES:-0}" \
    --build-env-vars-file "$build_env_file"

  FRONTEND_URL=$(gcloud run services describe "$FRONTEND_SERVICE" --region "$REGION" --format='value(status.url)')
  echo "フロントエンド: $FRONTEND_URL"

  echo "=== バックエンドの CORS をフロントのURLへ更新します ==="
  gcloud run services update "$BACKEND_SERVICE" --region "$REGION" --quiet \
    --update-env-vars "CORS_ORIGINS=$FRONTEND_URL"

  echo
  echo "残りの手動作業: Google Maps キーのリファラー制限に ${FRONTEND_URL}/* を追加する"
}

case "$TARGET" in
  backend) deploy_backend ;;
  frontend) deploy_frontend ;;
  all)
    deploy_backend
    deploy_frontend
    ;;
  *)
    echo "使い方: $0 [backend|frontend|all]" >&2
    exit 1
    ;;
esac
