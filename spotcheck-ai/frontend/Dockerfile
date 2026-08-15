# SpotCheck AI フロントエンド（Next.js）を Cloud Run で動かすためのイメージ。
#
# - `output: "standalone"`（next.config.mjs）で必要なファイルだけを取り出し、実行イメージを小さくする
# - **NEXT_PUBLIC_* はビルド時に埋め込まれる**ため、APIのURLと地図キーはビルド引数で渡す
# - Cloud Run は環境変数 PORT で待受ポートを渡してくる

FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# ブラウザへ露出する値。ビルド時に埋め込まれる
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_GOOGLE_MAPS_API_KEY
ARG NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT
ARG NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=$NEXT_PUBLIC_GOOGLE_MAPS_API_KEY \
    NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT=$NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT \
    NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG=$NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG

RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=8080

# standalone 出力には必要な node_modules が同梱されるが、public/ と
# .next/static は含まれないため、実行イメージへ明示的にコピーする。
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 8080
CMD ["sh", "-c", "node server.js"]
