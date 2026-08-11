# SpotCheck AI バックエンド（FastAPI）を Cloud Run で動かすためのイメージ。
#
# - YOLO（ultralytics）を同梱するため、OpenCV が必要とする共有ライブラリを入れる
# - 重み（models_weights/*.pt）はイメージへ焼き込む。無い場合はマスキングをスキップして動く
# - Cloud Run は環境変数 PORT で待受ポートを渡してくるため、それに従う

FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# OpenCV（ultralytics 依存）の実行に必要な最小限のライブラリ
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存だけを先に入れ、ソース変更でこの重いレイヤ（PyTorch を含む）が無効化されないようにする。
# `pip install .` はパッケージ本体（app/）を要求するため使わない。
# 実行は /app 直下から `uvicorn app.main:app` で行うので、本体のインストールは不要。
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt && \
    pip install -r /tmp/requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
# 重みは任意。存在すればコピーされる（`models_weights/` 自体は必ず作る）
COPY models_weights ./models_weights

# Cloud Run は $PORT（既定8080）で待ち受けることを要求する
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
