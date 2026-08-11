"""deploy/env.sh の DATABASE_URL を設定する。

    cd spotcheck-ai && python3 deploy/set_db_url.py            # 入力を促す
    cd spotcheck-ai && python3 deploy/set_db_url.py 'パスワード'  # 引数で渡す

- パスワードは入力時に画面へ表示されない（getpass）
- `@` `:` `/` `#` などを含むパスワードでも壊れないようURLエンコードする
- SQLAlchemy 用に `postgresql+psycopg://` へ書き換える

接続文字列は Supabase Dashboard の「Connect」→ Transaction pooler から取得する。
"""

from __future__ import annotations

import getpass
import pathlib
import re
import sys
from urllib.parse import quote

ENV_PATH = pathlib.Path(__file__).resolve().parent / "env.sh"
#: Supabase の接続文字列（パスワード以外）。Connect 画面の値に合わせている
DEFAULT_TEMPLATE = (
    "postgresql+psycopg://postgres.ghnjpjvjbxybqqdognar:{password}"
    "@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres"
)


def main() -> int:
    if not ENV_PATH.exists():
        print(f"{ENV_PATH} がありません。deploy/env.example.sh からコピーしてください。")
        return 1

    # 引数で渡された場合はそれを使う（対話が使えない環境向け）
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        print("Supabase のDBパスワードを入力してください。")
        print("分からない場合は Dashboard → Project Settings → Database → Reset database password で再発行できます。")
        try:
            # 端末があれば入力を隠す。`!` 経由など端末が無い場合は通常の入力へ落とす
            password = getpass.getpass("DB password: ")
        except Exception:
            password = input("DB password: ")

    if not password:
        print("入力が空のため中止しました。")
        return 1

    # パスワードに記号が含まれても壊れないようにエンコードする
    url = DEFAULT_TEMPLATE.format(password=quote(password, safe=""))

    text = ENV_PATH.read_text()
    if re.search(r"^DATABASE_URL=", text, flags=re.MULTILINE):
        text = re.sub(r'^DATABASE_URL="?[^"\n]*"?', f'DATABASE_URL="{url}"', text, flags=re.MULTILINE)
    else:
        text = text.rstrip() + f'\nDATABASE_URL="{url}"\n'
    ENV_PATH.write_text(text)

    masked = url.replace(quote(password, safe=""), "*" * 8)
    print("\ndeploy/env.sh へ書き込みました:")
    print(f"  DATABASE_URL={masked}")
    print("\n次はこのまま Claude に「入れた」と伝えてください。接続確認からデプロイまで進めます。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
