"""本番URLのQRコードを生成する（READMEに貼る用）。

    cd spotcheck-ai && ./backend/.venv/bin/python deploy/make_qr.py

出力先: docs/assets/demo-qr.png
URLを変えたら引数で渡す:
    ./backend/.venv/bin/python deploy/make_qr.py https://example.run.app
"""

from __future__ import annotations

import pathlib
import sys

import qrcode
from qrcode.constants import ERROR_CORRECT_M

DEFAULT_URL = "https://spotcheck-frontend-dathtekrwq-an.a.run.app"
OUT_PATH = pathlib.Path(__file__).resolve().parents[1] / "docs/assets/demo-qr.png"


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    qr = qrcode.QRCode(
        version=None,
        # スマホのカメラで読み取りやすいよう、誤り訂正は中程度にする
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    qr.make_image(fill_color="black", back_color="white").save(OUT_PATH)

    print(f"URL: {url}")
    print(f"出力: {OUT_PATH}（{OUT_PATH.stat().st_size} バイト）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
