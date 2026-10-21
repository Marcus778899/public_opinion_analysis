"""發版工具：一個階段完成後，develop 合回 main 並打 tag。

用法：
    release.py open <vX.Y.Z>     # 檢查：任務都已合併、資安審查 PASS 且審的就是要發的程式、UAT 甲方驗收清單全勾且寫了 PASS → 開 develop→main 的 PR
    release.py finish <vX.Y.Z>   # CI 綠才合併（merge commit）→ 在 main 打 tag → 建 GitHub release
                                 # → 本機把 main 併回 develop 並 push
                                 # → 封存布告欄與派工單到 tasks/<vX.Y.Z>（board.py archive）並提交到 develop

main 併回 develop 由這支在本機做完（緊接著要提交封存，交給非同步的 workflow 會跟這裡的 push 互搶）；
.github/workflows/sync_branch.yml 只是保底（例：在 GitHub 網頁上合進 main），develop 已包含 main 就什麼都不做。
exit code：0 成功；1 條件不符或指令失敗
"""

import argparse
import json
import re

from _common import (
    BASE_BRANCH,
    RELEASE_BRANCH,
    ROOT,
    TASKS_DIR,
    FlowError,
    check_integrity,
    fail,
    number_from_url,
    require_on_base,
    run,
    run_status,
)
from board import BoardError, archive
from docs import commit as commit_docs
from pr import check_ci

VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
UAT_DIR = ROOT / "docs" / "uat"
SECURITY_DIR = ROOT / "docs" / "security"
# 審查之後只能多這些（文件）：其他檔案有變，就代表發出去的程式不是審過的那一份
POST_REVIEW_PATHS = ("docs/", "BOARD.md", "README.md")
SIGNOFF_HEADING = "## 甲方驗收清單"
SIGNOFF_PASS = "甲方驗收：PASS"


def release_meta_path(version: str):
    return TASKS_DIR / f"release-{version}.json"


def check_uat(version: str) -> None:
    path = UAT_DIR / f"{version}.md"
    if not path.exists():
        raise FlowError(f"找不到 {path.relative_to(ROOT)}；先派 uat 做使用者測試")
    text = path.read_text(encoding="utf-8")
    if SIGNOFF_HEADING not in text:
        raise FlowError(f"{path.name} 缺少「{SIGNOFF_HEADING}」")
    signoff = text.split(SIGNOFF_HEADING, 1)[1]
    unchecked = [line.strip() for line in signoff.splitlines() if line.strip().startswith("- [ ]")]
    if unchecked:
        raise FlowError("甲方驗收清單還有沒勾的項目：\n" + "\n".join(unchecked))
    if SIGNOFF_PASS not in signoff:
        raise FlowError(f"甲方尚未在 {path.name} 寫下「{SIGNOFF_PASS}」")


def check_security(version: str) -> None:
    """security 的報告第一行「PASS <commit>」，且那個 commit 之後只多了文件。"""
    path = SECURITY_DIR / f"{version}.md"
    rel = path.relative_to(ROOT)
    if not path.exists():
        raise FlowError(f"找不到 {rel}：先派 security 做發版前資安審查")
    first = path.read_text(encoding="utf-8").strip().split("\n", 1)[0].split()
    if len(first) != 2 or first[0] not in ("PASS", "FAIL"):
        raise FlowError(f"{rel} 第一行必須是「PASS／FAIL <commit>」")
    verdict, reviewed = first
    if verdict == "FAIL":
        raise FlowError(f"資安審查 FAIL（{rel}）：critical／high 的問題開 fix 單修完、合併後，再派 security 重審")
    if run_status("git", "cat-file", "-e", f"{reviewed}^{{commit}}")[0] != 0:
        raise FlowError(f"{rel} 的 commit {reviewed} 不存在")
    changed = run("git", "diff", "--name-only", f"{reviewed}..HEAD").splitlines()
    code = [f for f in changed if not any(f == p or (p.endswith("/") and f.startswith(p)) for p in POST_REVIEW_PATHS)]
    if code:
        raise FlowError(f"資安審查之後程式又變了（{'、'.join(code[:5])}…）：再派 security 審到最新的 develop")


def check_tasks_merged() -> None:
    pending = []
    for path in TASKS_DIR.glob("*.meta.json"):
        meta = json.loads(path.read_text(encoding="utf-8"))
        if not meta.get("merged") and not meta.get("cancelled"):
            pending.append(meta["task_id"])
    if pending:
        raise FlowError(f"還有沒合併的任務：{', '.join(sorted(pending))}（不做的用 task.py cancel 作廢）")


def open_release(version: str) -> None:
    if not VERSION_RE.match(version):
        raise FlowError("版本格式要是 vX.Y.Z")
    if run("git", "ls-remote", "--tags", "origin", version):
        raise FlowError(f"tag {version} 已存在")
    require_on_base()
    if run("git", "status", "--porcelain"):
        raise FlowError("主目錄有沒提交的修改；文件先用 docs.py commit，其他走派工單")
    check_tasks_merged()
    run("git", "pull", "--ff-only", "origin", BASE_BRANCH)
    check_security(version)
    check_uat(version)
    body = f"階段發版 {version}\n\n使用者測試與甲方驗收：`docs/uat/{version}.md`\n\n資安審查：`docs/security/{version}.md`"
    url = run("gh", "pr", "create", "--base", RELEASE_BRANCH, "--head", BASE_BRANCH, "--title", f"release: {version}", "--body", body)
    pr = number_from_url(url)
    release_meta_path(version).write_text(json.dumps({"version": version, "pr": pr}) + "\n", encoding="utf-8")
    print(f"發版 PR #{pr}：{url}")


def finish_release(version: str) -> None:
    path = release_meta_path(version)
    if not path.exists():
        raise FlowError("先執行 release.py open")
    pr = json.loads(path.read_text(encoding="utf-8"))["pr"]
    require_on_base()
    check_ci(pr)
    run("gh", "pr", "merge", str(pr), "--merge")
    run("git", "fetch", "origin")
    run("git", "tag", "-a", version, f"origin/{RELEASE_BRANCH}", "-m", f"release {version}")
    run("git", "push", "origin", version)
    run("gh", "release", "create", version, "--verify-tag", "--generate-notes", "--title", version)
    run("git", "pull", "--ff-only", "origin", BASE_BRANCH)
    run("git", "merge", "--no-edit", f"origin/{RELEASE_BRANCH}")  # 通常是 fast-forward
    run("git", "push", "origin", BASE_BRANCH)
    print(f"{version} 已合併到 {RELEASE_BRANCH} 並打 tag，{BASE_BRANCH} 已同步")
    try:
        archive(version)
        commit_docs(f"封存 {version} 布告欄與派工單")
    except (BoardError, FlowError) as e:
        archived = (TASKS_DIR / f"{version}.md").exists()
        todo = "" if archived else f"board.py archive {version}，再執行 "
        raise FlowError(f"發版已完成，但封存沒做完：{e}\n處理後執行 {todo}docs.py commit \"封存 {version} 布告欄與派工單\"") from e


def main() -> None:
    parser = argparse.ArgumentParser(description="發版工具")
    parser.add_argument("action", choices=("open", "finish"))
    parser.add_argument("version")
    args = parser.parse_args()
    try:
        check_integrity()
        if args.action == "open":
            open_release(args.version)
        else:
            finish_release(args.version)
    except FlowError as e:
        fail(str(e))


if __name__ == "__main__":
    main()
