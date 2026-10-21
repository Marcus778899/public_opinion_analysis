"""CI 用：這個 PR 改到的程式碼，至少 MIN_PERCENT% 的行要被測試執行到（diff-cover）。

用法：coverage_gate.py <base>      # CI：origin/develop；先跑過 make coverage

為什麼看「改到的程式碼」而不是總覆蓋率：總數只升不降會被早期的小程式綁架（98% 的骨架之後，
認真寫到 92% 的新功能也會讓總數下降而被擋），逼人寫湊數測試；只看這次的改動，每個 PR 標準一樣。

報告：make coverage 把報告寫到 coverage-reports/*.xml，一律 XML（Cobertura 或 JaCoCo；diff-cover 不能混用 LCOV 與 XML），
路徑要能對到 repo 根目錄的相對路徑。JaCoCo 的原始碼目錄用環境變數 COVERAGE_SRC_ROOTS（空白分隔）指定。

diff-cover 對「不在報告裡的檔案」不算行數：報告路徑對不上、或只設了後端覆蓋率而前端報告整份沒產出，
它會當成 100% 通過，設定錯了反而永遠綠。所以改到的程式檔一定要在報告裡（拿整個檔案再量一次確認），
不在就失敗；本來就不量的檔案（設定檔、migration、產生的程式）列在 EXEMPT，專案自己的放 .coverage-exempt
（一行一個 fnmatch 樣式，* 也比對 /；它是 fast 通道的受保護路徑，加一條要 architect review）。

exit code：0 通過；1 不通過或設定錯誤
"""

import ast
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _common import ROOT, TEST_PATTERNS, FlowError, fail, run

MIN_PERCENT = 80.0
REPORT_DIR = ROOT / "coverage-reports"
EXEMPT_FILE = ROOT / ".coverage-exempt"
# 通常不在覆蓋率報告裡的程式檔
EXEMPT = (
    "*.config.*", "*.d.ts", "*migration*", "*/migrate/*", "*/generated/*", "*_pb2.py", "*.pb.go",
    "*conftest.py", "manage.py", "*/manage.py", "*/wsgi.py", "*/asgi.py",
)
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
# 算成「程式碼」的副檔名；測試檔（TEST_PATTERNS）不算
CODE_EXT = (
    ".py", ".go", ".java", ".kt", ".scala", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte",
    ".rb", ".rs", ".cs", ".php",
)


def exempt_patterns() -> tuple[str, ...]:
    if not EXEMPT_FILE.is_file():
        return EXEMPT
    lines = EXEMPT_FILE.read_text(encoding="utf-8").splitlines()
    return EXEMPT + tuple(l.strip() for l in lines if l.strip() and not l.startswith("#"))


def changed_code(base: str) -> list[str]:
    files = run("git", "diff", "--name-only", "--diff-filter=AMR", f"{base}...HEAD").splitlines()
    skip = TEST_PATTERNS + exempt_patterns()
    code = [f for f in files if f.endswith(CODE_EXT) and not any(fnmatch.fnmatch(f, pat) for pat in skip)]
    return [f for f in code if has_statements(f)]


def has_statements(f: str) -> bool:
    """空檔、只有註解或 docstring 的 .py（常見於 __init__.py）沒有可執行的行，報告裡永遠量不到。
    不整個豁免 __init__.py：裡面寫了程式（例：create_app）一樣要量。"""
    text = (ROOT / f).read_text(encoding="utf-8", errors="ignore")
    if not f.endswith(".py"):
        return bool(text.strip())
    try:
        body = ast.parse(text).body
    except SyntaxError:
        return True
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return bool(body)


def measured(stats: dict, f: str) -> bool:
    return bool(stats.get(f, {}).get("covered_lines") or stats.get(f, {}).get("violation_lines"))


def not_in_report(reports: list[Path], files: list[str]) -> list[str]:
    """這次改到的行都不是可執行的行（例：只改註解）時 diff-cover 也是 0 行：拿整個檔案當成新增再量一次。"""
    if not files:
        return []  # 不指定路徑的 git diff 會變成整個 repo
    with tempfile.TemporaryDirectory() as tmp:
        whole = Path(tmp) / "whole.diff"
        whole.write_text(run("git", "diff", EMPTY_TREE, "HEAD", "--", *files) + "\n", encoding="utf-8")
        stats = diff_cover(reports, ["--diff-file", str(whole)])["src_stats"]
    return [f for f in files if not measured(stats, f)]


def diff_cover(reports: list[Path], compare: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "diff-cover.json"
        cmd = ["diff-cover", *map(str, reports), *compare, "--format", f"json:{out}", "--quiet"]
        roots = os.environ.get("COVERAGE_SRC_ROOTS", "").split()
        if roots:
            cmd += ["--src-roots", *roots]
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if result.returncode != 0 or not out.is_file():
            raise FlowError(f"diff-cover 執行失敗（exit {result.returncode}）：{(result.stderr or result.stdout).strip()}")
        return json.loads(out.read_text(encoding="utf-8"))


def main() -> None:
    if len(sys.argv) != 2:
        fail("用法：coverage_gate.py <base>（例：origin/develop）")
    base = sys.argv[1]
    try:
        code = changed_code(base)
        if not code:
            print("沒有改到程式碼（只有測試、文件或設定），略過覆蓋率檢查")
            return
        reports = sorted(REPORT_DIR.glob("*.xml"))
        if not reports:
            raise FlowError(f"{REPORT_DIR.name}/ 沒有 XML 報告：make coverage 要把 Cobertura／JaCoCo XML 寫到這裡")
        data = diff_cover(reports, ["--compare-branch", base])
        total = data["total_num_lines"]
        stats = data["src_stats"]
        missing = not_in_report(reports, [f for f in code if not measured(stats, f)])
        if missing:
            raise FlowError(
                "這些改到的程式檔不在覆蓋率報告裡：" + "、".join(missing) + "\n"
                "可能是：沒有任何測試載入它（補測試）；這一端的報告沒產出（例：只設了後端覆蓋率，make coverage 要涵蓋每一端）；"
                "報告路徑對不到 repo 根目錄（JaCoCo 要設 COVERAGE_SRC_ROOTS）；"
                f"本來就不該量（設定檔、進入點、只有型別宣告的檔）就加進 {EXEMPT_FILE.name}"
            )
        if total == 0:
            print("改到的都不是可執行的行（例：註解、型別宣告），略過")
            return
        percent = (total - data["total_num_violations"]) / total * 100
        if percent < MIN_PERCENT:
            lines = [
                f"  {f}：第 {', '.join(map(str, s['violation_lines'][:30]))} 行"
                for f, s in sorted(stats.items()) if s.get("violation_lines")
            ]
            raise FlowError(
                f"改到的程式碼覆蓋率 {percent:.1f}%（{total} 行），低於 {MIN_PERCENT:.0f}%：這些行沒有被任何測試執行到\n"
                + "\n".join(lines)
            )
        print(f"改到的程式碼覆蓋率 {percent:.1f}%（{total} 行），門檻 {MIN_PERCENT:.0f}%")
    except FlowError as e:
        fail(str(e))


if __name__ == "__main__":
    main()
