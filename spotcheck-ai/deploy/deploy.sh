#!/bin/bash
# SpotCheck AI を Google Cloud Run へデプロイする。
#
#   cd spotcheck-ai && ./deploy/deploy.sh            # バックエンド→フロントの順に両方
#   cd spotcheck-ai && ./deploy/deploy.sh backend    # バックエンドのみ
#   cd spotcheck-ai && ./deploy/deploy.sh frontend   # フロントのみ
#
# 前提:
# - gcloud にログイン済み（gcloud auth login）でプロジェクトを選択済み
# - deploy/env.sh に設定を書いてある（deploy/env.example.sh をコピーして作る）
# - DBは Supabase の PostgreSQL を使う（Cloud SQL は使わない）
set -euo pipefail

cd "$(dirname "$0")/.."
TARGET="${1:-all}"

if [ ! -f deploy/env.sh ]; then
  echo "deploy/env.sh がありません。deploy/env.example.sh をコピーして値を入れてください。" >&2
  exit 1
fi
# shellcheck disable=SC1091
source deploy/env.sh

: "${PROJECT_ID:?PROJECT_ID を deploy/env.sh に設定してください}"
: "${REGION:=asia-northeast1}"
: "${BACKEND_SERVICE:=spotcheck-backend}"
: "${FRONTEND_SERVICE:=spotcheck-frontend}"

echo "プロジェクト: $PROJECT_ID / リージョン: $REGION"
gcloud config set project "$PROJECT_ID" --quiet

deploy_backend() {
  : "${DATABASE_URL:?DATABASE_URL（Supabase の接続文字列）を設定してください}"
  : "${JWT_SECRET:?JWT_SECRET を設定してください}"

  echo "=== バックエンドをデプロイします（ビルドに10分前後かかります）==="
  # 環境変数はカンマを含むためデリミタを ^@^ に変えて渡す
  gcloud run deploy "$BACKEND_SERVICE" \
    --source backend \
    --region "$REGION" \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 900 \
    --concurrency 20 \
    --min-instances "${BACKEND_MIN_INSTANCES:-0}" \
    --set-env-vars "^@^APP_ENV=production@DATABASE_URL=${DATABASE_URL}@JWT_SECRET=${JWT_SECRET}@SUPABASE_URL=${SUPABASE_URL:-}@SUPABASE_SECRET_KEY=${SUPABASE_SECRET_KEY:-}@ORCA_API_KEY=${ORCA_API_KEY:-}@ORCA_STUB_MODE=${ORCA_STUB_MODE:-true}@GOOGLE_MAPS_SERVER_API_KEY=${GOOGLE_MAPS_SERVER_API_KEY:-}@ORCA_ROUTER_IMAGE=${ORCA_ROUTER_IMAGE:-}@CORS_ORIGINS=${CORS_ORIGINS:-*}"

  BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE" --region "$REGION" --format='value(status.url)')
  echo "バックエンド: $BACKEND_URL"
}

deploy_frontend() {
  BACKEND_URL="${BACKEND_URL:-$(gcloud run services describe "$BACKEND_SERVICE" --region "$REGION" --format='value(status.url)' 2>/dev/null || true)}"
  : "${BACKEND_URL:?バックエンドのURLが取得できません。先にバックエンドをデプロイしてください}"

  echo "=== フロントエンドをデプロイします（APIの向き先: $BACKEND_URL）==="
  gcloud run deploy "$FRONTEND_SERVICE" \
    --source frontend \
    --region "$REGION" \
    --allow-unauthenticated \
    --memory 1Gi \
    --min-instances "${FRONTEND_MIN_INSTANCES:-0}" \
    --build-env-vars "^@^NEXT_PUBLIC_API_BASE_URL=${BACKEND_URL}@NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=${NEXT_PUBLIC_GOOGLE_MAPS_API_KEY:-}@NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT=${NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT:-35.6595}@NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG=${NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG:-139.7005}"

  FRONTEND_URL=$(gcloud run services describe "$FRONTEND_SERVICE" --region "$REGION" --format='value(status.url)')
  echo "フロントエンド: $FRONTEND_URL"

  echo
  echo "次の2つを忘れずに:"
  echo "  1. バックエンドの CORS_ORIGINS に $FRONTEND_URL を設定する"
  echo "     gcloud run services update $BACKEND_SERVICE --region $REGION --update-env-vars CORS_ORIGINS=$FRONTEND_URL"
  echo "  2. Google Maps キーのリファラー制限に ${FRONTEND_URL}/* を追加する"
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
