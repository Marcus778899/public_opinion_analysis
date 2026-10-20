"""檢查甲方要填的設定（.env）是否都填了。只印變數名稱，絕不印出值。

.env.example 是設定清單（可 commit）：每行 `KEY=預設值`，上一行的 `#` 註解是說明。
值為空或含 CHANGE_ME 的，代表一定要甲方決定；選填設定寫成註解 `# KEY=`，不列入檢查。

sandbox 擋住所有 `.env`（連存在與否都查不到）：甲方在自己的終端機（sandbox 外）跑本腳本，
設定齊全時記下 .env.example 的雜湊（不含值）；sandbox 內讀不到 .env 時改比對這個雜湊。

用法：
    check_env.py      # .env 不存在就從 .env.example 複製一份；列出還沒填的變數
    check_env.py setup  # 在主目錄跑 make setup，記下相依檔雜湊；develop 的相依變了沒重裝，task.py new 會拒絕開單

exit code：0 全部填好／安裝成功；1 還有沒填的（manager 要停下來請甲方填）或安裝失敗
"""

import argparse
import hashlib
import re
import shutil
import subprocess
import sys

from _common import DEPS_STAMP, ROOT, WORKTREES_DIR, deps_hash, require_on_base

EXAMPLE = ROOT / ".env.example"
ENV = ROOT / ".env"
# 甲方在 sandbox 外確認設定齊全時，對應的 .env.example 雜湊
ENV_STAMP = WORKTREES_DIR / ".env-stamp"
PLACEHOLDER = "CHANGE_ME"
# 選填設定 `# KEY=值`：不是說明，不能接到下一個變數上
OPTIONAL_RE = re.compile(r"^#\s*[A-Za-z_][A-Za-z0-9_]*=")
OUTSIDE_SANDBOX_HINT = "請甲方在自己的終端機（sandbox 外）跑 python3 scripts/check_env.py"


def parse(path) -> dict[str, tuple[str, str]]:
    """回傳 {KEY: (值, 說明)}。"""
    entries: dict[str, tuple[str, str]] = {}
    comment = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if OPTIONAL_RE.match(line):
            comment = ""
        elif line.startswith("#"):
            comment = line.lstrip("# ")
        elif "=" in line:
            key, value = line.split("=", 1)
            entries[key.strip()] = (value.strip().strip('"').strip("'"), comment)
            comment = ""
        else:
            comment = ""
    return entries


def example_hash() -> str:
    return hashlib.sha256(EXAMPLE.read_bytes()).hexdigest()


def missing_settings() -> list[str]:
    """回傳還沒填的變數（含說明），不會建立或修改任何檔案。"""
    if not EXAMPLE.exists():
        return []
    try:
        actual = parse(ENV) if ENV.exists() else {}
    except PermissionError:
        # sandbox 內：只能看甲方上次確認時的 .env.example 有沒有變
        stamp = ENV_STAMP.read_text(encoding="utf-8").strip() if ENV_STAMP.exists() else ""
        if stamp == example_hash():
            return []
        return [f"- sandbox 內讀不到 .env，且 .env.example 在甲方上次確認後變了（或從沒確認過）：{OUTSIDE_SANDBOX_HINT}"]
    missing = []
    for key, (_, comment) in parse(EXAMPLE).items():
        value = actual.get(key, ("", ""))[0]
        if not value or PLACEHOLDER in value:
            missing.append(f"- {key}：{comment}" if comment else f"- {key}")
    return missing


def deps_outdated() -> bool:
    """develop 的相依檔跟上次 setup 時不同（或從沒 setup 過）。沒有 Makefile 或相依檔就不需要。"""
    current = deps_hash()
    if not current or not (ROOT / "Makefile").exists():
        return False
    stamp = DEPS_STAMP.read_text(encoding="utf-8").strip() if DEPS_STAMP.exists() else ""
    return stamp != current


def setup() -> None:
    require_on_base()
    result = subprocess.run(("make", "setup"), cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-20:])
        print(f"make setup 失敗（exit {result.returncode}），最後 20 行：\n{tail}", file=sys.stderr)
        sys.exit(1)
    DEPS_STAMP.parent.mkdir(exist_ok=True)
    DEPS_STAMP.write_text(deps_hash() + "\n", encoding="utf-8")
    print("make setup 完成，已記錄相依版本（所有 worktree 共用這份環境）")


def main() -> None:
    parser = argparse.ArgumentParser(description="設定與環境檢查")
    parser.add_argument("action", nargs="?", choices=("setup",))
    if parser.parse_args().action == "setup":
        setup()
        return
    if not EXAMPLE.exists():
        print("沒有 .env.example，這個專案不需要設定")
        return
    try:
        env_exists = ENV.exists()
        if env_exists:
            ENV.read_bytes()  # 有的 sandbox 查得到存在、讀不到內容
    except PermissionError:
        missing = missing_settings()
        if missing:
            print("\n".join(missing), file=sys.stderr)
            sys.exit(1)
        print("sandbox 內讀不到 .env；甲方已確認過目前的 .env.example，設定齊全")
        return
    if not env_exists:
        shutil.copy(EXAMPLE, ENV)
        print("已從 .env.example 建立 .env")
    example = parse(EXAMPLE)
    missing = missing_settings()
    if missing:
        print(f"請甲方在 {ENV.relative_to(ROOT)} 填入以下設定，填完再繼續：", file=sys.stderr)
        print("\n".join(missing), file=sys.stderr)
        sys.exit(1)
    ENV_STAMP.parent.mkdir(exist_ok=True)
    ENV_STAMP.write_text(example_hash() + "\n", encoding="utf-8")
    print(f"設定齊全（{len(example)} 項）")


if __name__ == "__main__":
    main()
