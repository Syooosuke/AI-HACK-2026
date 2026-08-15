# SpotCheck AI バックエンド（FastAPI）を Cloud Run で動かすためのイメージ。
#
# - YOLO（ultralytics）を同梱するため、OpenCV が必要とする共有ライブラリを入れる
# - YOLO重みは固定URLから取得・検証し、イメージへ焼き込む
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

# **CPU版の PyTorch を先に入れる。**
# ultralytics は既定でCUDA付きの torch を引くが、Cloud Run はGPUを持たないため
# 数GBの CUDA ライブラリが完全に無駄になる（イメージ肥大・ビルド失敗・起動遅延の原因）。
# 先にCPU版を入れておけば、あとから ultralytics を入れても torch は再解決されない。
RUN pip install --upgrade pip && \
    pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision

# 依存だけを先に入れ、ソース変更でこの重いレイヤが無効化されないようにする。
# `pip install .` はパッケージ本体（app/）を要求するため使わない。
# 実行は /app 直下から `uvicorn app.main:app` で行うので、本体のインストールは不要。
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt && \
    pip install -r /tmp/requirements.txt

# Gitには置かないYOLO重みを取得し、SHA-256検証後にイメージへ含める。
# スクリプトだけを先にコピーして、アプリ変更時にもこのレイヤを再利用する。
COPY scripts/download_yolo_models.py ./scripts/download_yolo_models.py
RUN python scripts/download_yolo_models.py

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# Cloud Run は $PORT（既定8080）で待ち受けることを要求する
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
