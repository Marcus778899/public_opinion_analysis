"""派工單工具：manager 透過它開工。一張派工單 = 一個 GitHub issue = 一個分支 = 一個 worktree。

task_id 就是分支與工作目錄的名字，要看得出在做什麼：小寫英數、用 - 連接、至少兩個字，
例 `todo-create-api`、`trip-list-click`；不可有純數字段（`ui-02`）、不可用類型開頭（`fix-login` → `fix/fix-login`）。
分支 `<類型>/<task_id>`，工作目錄 `.worktrees/<task_id>`。

用法（內容從 stdin 傳入，格式依 templates/task-card.md）：
    task.py new <task_id>     < card.md    # 檢查格式 → 寫 tasks/<id>.md → 開 issue → 從 develop 開分支與 worktree
    task.py amend <task_id>   < note.md    # 追加內容（例：qa FAIL 的重現步驟），同步留言到 issue；分支沒有新 commit 前不能再追加（一輪一次）
    task.py amend <task_id> --from reports/<id>.qa.md reports/<id>.review.md [-]
                                           # 直接用 qa／review 的證據檔追加，不用再打一次；- 代表另外從 stdin 補充（例：甲方意見）
    task.py cancel <task_id>  < 原因       # 作廢：關 PR 與 issue、刪 worktree 與分支；release.py 會略過作廢的單

沒有 origin remote 時只建本機分支，不開 issue。
exit code：0 成功；1 格式錯誤或狀態不對
"""

import argparse
import re
import sys
from datetime import datetime, timezone

from check_env import deps_outdated, missing_settings
from _common import (
    BASE_BRANCH,
    BRANCH_TYPES,
    ROOT,
    TASKS_DIR,
    WORKTREES_DIR,
    FlowError,
    check_integrity,
    fail,
    has_remote,
    load_meta,
    number_from_url,
    require_on_base,
    run,
    save_meta,
)

REQUIRED_FIELDS = ("類型", "負責", "目標", "背景", "設計依據", "相依", "負責檔案", "禁區", "驗收測試", "驗收條件", "驗證指令", "回報檔")
PLACEHOLDERS = ("path/to/file.py", "path/to/acceptance/", "條件一", "一句話", "<task_id>", "feat / fix", "backend / frontend / architect / designer")
MAX_CARD_LINES = 40
MAX_BACKGROUND_LINES = 5
# worktree 需要、但不進 git 的東西，用 symlink 共用主目錄的
SHARED_PATHS = (".venv", "node_modules", ".env")
# 派工前必須已提交：worker 的 worktree 從 develop 開出，只看得到已提交的決策
DISPATCH_DOCS = ("BOARD.md", "docs/decisions.md")
FIELD_RE = re.compile(r"^- \*\*(.+?)\*\*[：:]?\s*(.*)$")
BACKTICK_RE = re.compile(r"`([^`]+)`")
# 這些類型要先由 qa 寫驗收測試
TDD_KINDS = ("feat", "fix")
# 通道：full＝完整流程；fast＝小修改，不用先寫驗收測試、不用 architect review（範圍、qa 驗證、CI 照舊；超出條件 pr.py 自動升級）
LANES = ("full", "fast")
FAST_FORBIDDEN_OWNERS = ("architect", "designer")
TASK_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")
MAX_TASK_ID_LEN = 40
# 封存資料夾用版本號命名（tasks/v0.1.0/），task_id 不可撞名
VERSION_LIKE_RE = re.compile(r"^v\d")


def check_task_id(task_id: str, kind: str = "") -> list[str]:
    """task_id 會變成分支與 worktree 名稱，必須有意義。"""
    example = "例：todo-create-api、trip-list-click"
    if not TASK_ID_RE.match(task_id) or len(task_id) > MAX_TASK_ID_LEN:
        return [f"task_id「{task_id}」要是小寫英數、用 - 連接、至少兩個字、最長 {MAX_TASK_ID_LEN} 字元（{example}）"]
    problems = []
    if any(part.isdigit() for part in task_id.split("-")):
        problems.append(f"task_id「{task_id}」不可有流水號，用名稱說明在做什麼（{example}）")
    if VERSION_LIKE_RE.match(task_id):
        problems.append(f"task_id「{task_id}」不可用 v+數字開頭（會跟版本封存資料夾撞名）")
    if kind and task_id.startswith(f"{kind}-"):
        problems.append(f"task_id 不要用類型開頭（分支會變成 {kind}/{task_id}）；拿掉「{kind}-」，用功能與動作命名")
    return problems


def branch_exists(branch: str) -> bool:
    if run("git", "branch", "--list", branch):
        return True
    return has_remote() and bool(run("git", "ls-remote", "--heads", "origin", branch))


def field_paths(fields: dict[str, list[str]], field: str) -> list[str]:
    """欄位裡用反引號標出的路徑（「負責檔案」「驗收測試」）；寫「無」就是空的。"""
    return [p for line in fields.get(field, []) for p in BACKTICK_RE.findall(line)]


def acceptance_paths(fields: dict[str, list[str]]) -> list[str]:
    return field_paths(fields, "驗收測試")


def card_paths(task_id: str, field: str) -> list[str]:
    path = TASKS_DIR / f"{task_id}.md"
    if not path.exists():
        return []
    return field_paths(parse_fields(path.read_text(encoding="utf-8")), field)


def card_acceptance_paths(task_id: str) -> list[str]:
    return card_paths(task_id, "驗收測試")


def parse_fields(body: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    current = None
    for line in body.splitlines():
        match = FIELD_RE.match(line)
        if match:
            current = match.group(1)
            fields[current] = [match.group(2).strip()] if match.group(2).strip() else []
        elif line.startswith("#"):
            current = None
        elif current and line.strip():
            fields[current].append(line.strip())
    return fields


def card_lane(fields: dict[str, list[str]]) -> str:
    """「通道」欄位可省略，預設 full。"""
    return " ".join(fields.get("通道", [])) or "full"


def check_card(task_id: str, body: str) -> list[str]:
    fields = parse_fields(body)
    problems = [f"缺少欄位「{f}」" for f in REQUIRED_FIELDS if f not in fields]
    problems += [f"還留著模板佔位字「{p}」" for p in PLACEHOLDERS if p in body]
    if f"reports/{task_id}.json" not in body:
        problems.append(f"回報檔必須是 reports/{task_id}.json")
    kind = " ".join(fields.get("類型", []))
    if kind and kind not in BRANCH_TYPES:
        problems.append(f"類型必須是 {'/'.join(BRANCH_TYPES)} 其中一個，實際是「{kind}」")
    problems += check_task_id(task_id, kind)
    lane = card_lane(fields)
    if lane not in LANES:
        problems.append(f"通道必須是 {'/'.join(LANES)}，實際是「{lane}」")
    if lane == "fast" and " ".join(fields.get("負責", [])) in FAST_FORBIDDEN_OWNERS:
        problems.append("設計類任務（architect／designer）不可走 fast 通道")
    if kind in TDD_KINDS and lane != "fast" and "驗收測試" in fields and not acceptance_paths(fields):
        problems.append(f"{kind} 單要列出「驗收測試」目錄（qa 先寫測試，worker 再實作）")
    lines = [line for line in body.splitlines() if line.strip()]
    if len(lines) > MAX_CARD_LINES:
        problems.append(f"派工單 {len(lines)} 行，上限 {MAX_CARD_LINES}；背景改用引用（見 docs/... §N），不要重講契約")
    if len(fields.get("背景", [])) > MAX_BACKGROUND_LINES:
        problems.append(f"背景超過 {MAX_BACKGROUND_LINES} 行")
    return problems


def start_worktree(task_id: str, kind: str) -> tuple[str, str]:
    branch = f"{kind}/{task_id}"
    if branch_exists(branch):
        raise FlowError(f"分支 {branch} 已存在（之前的版本用過這個名字）；task_id 換個更具體的名字")
    path = WORKTREES_DIR / task_id
    run("git", "worktree", "add", "-b", branch, str(path), BASE_BRANCH)
    for name in SHARED_PATHS:
        if (ROOT / name).exists() and not (path / name).exists():
            (path / name).symlink_to(ROOT / name)
    return branch, str(path.relative_to(ROOT))


def new_card(task_id: str, body: str) -> None:
    path = TASKS_DIR / f"{task_id}.md"
    if path.exists():
        raise FlowError(f"{path.relative_to(ROOT)} 已存在；要補充內容請用 amend")
    problems = check_card(task_id, body)
    if problems:
        raise FlowError("；".join(problems))
    require_on_base()
    pending_docs = run("git", "status", "--porcelain", "--", *DISPATCH_DOCS)
    if pending_docs:
        raise FlowError("布告欄或決策紀錄還沒提交，worker 從 develop 開分支會看不到：先 docs.py commit")
    missing = missing_settings()
    if missing:
        raise FlowError("甲方還沒填好 .env，不能開工；請甲方填入以下設定：\n" + "\n".join(missing))
    if has_remote():
        run("git", "pull", "--ff-only", "origin", BASE_BRANCH)
    if deps_outdated():
        raise FlowError("develop 的相依檔跟主目錄環境不一致（有單改了相依）：先 check_env.py setup 重裝，worktree 共用這份環境")

    fields = parse_fields(body)
    kind = fields["類型"][0]
    title = fields["目標"][0]
    heading = f"# 派工單 {task_id}"
    if not body.lstrip().startswith(heading):
        body = f"{heading}\n\n{body.lstrip()}"
    TASKS_DIR.mkdir(exist_ok=True)
    path.write_text(body.rstrip() + "\n", encoding="utf-8")

    branch, worktree = start_worktree(task_id, kind)
    issue = None
    if has_remote():
        url = run("gh", "issue", "create", "--title", f"[{task_id}] {title}", "--body-file", str(path), "--label", kind)
        issue = number_from_url(url)
    else:
        print("警告：沒有 origin remote，未開 issue", file=sys.stderr)

    with path.open("a", encoding="utf-8") as f:
        f.write("\n## 執行資訊（task.py 產生）\n\n")
        if issue:
            f.write(f"- Issue：#{issue}\n")
        f.write(f"- 分支：`{branch}`（從 {BASE_BRANCH} 開出）\n")
        f.write(f"- 工作目錄：`{worktree}`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`\n")

    save_meta({
        "task_id": task_id,
        "kind": kind,
        "owner": fields["負責"][0],
        "lane": card_lane(fields),
        "title": title,
        "issue": issue,
        "branch": branch,
        "worktree": worktree,
        "pr": None,
        "qa": None,
        "review": None,
        "merged": False,
    })
    print(f"派工單：{path.relative_to(ROOT)}")
    print(f"Issue：#{issue}" if issue else "Issue：（無 remote）")
    print(f"分支：{branch}（通道：{card_lane(fields)}）")
    print(f"工作目錄：{worktree}")


def read_sources(sources: list[str]) -> str:
    """--from 的檔案依序接起來；- 是 stdin。"""
    parts = []
    for src in sources:
        if src == "-":
            parts.append(sys.stdin.read().strip())
            continue
        path = ROOT / src
        if not path.is_file():
            raise FlowError(f"找不到 {src}")
        parts.append(f"### {src}\n\n{path.read_text(encoding='utf-8').strip()}")
    return "\n\n".join(p for p in parts if p)


def amend_card(task_id: str, body: str) -> None:
    path = TASKS_DIR / f"{task_id}.md"
    if not path.exists():
        raise FlowError(f"{path.relative_to(ROOT)} 不存在；先用 new 建立")
    if not body.strip():
        raise FlowError("追加內容是空的")
    meta = load_meta(task_id)
    sha = run("git", "rev-parse", meta["branch"])
    if meta.get("amend_sha") == sha:
        raise FlowError(
            "這一輪已經追加過（分支還沒有新 commit）：把 qa 與 review 的所有問題合併成一次追加；"
            "要補充就先等 worker 修完這一輪"
        )
    today = datetime.now(timezone.utc).date().isoformat()
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n## 追加 {today}\n\n{body.strip()}\n")
    meta["amend_sha"] = sha
    save_meta(meta)
    issue = meta.get("issue")
    if issue:
        run("gh", "issue", "comment", str(issue), "--body", f"**派工單追加 {today}**\n\n{body.strip()}")
    print(path.relative_to(ROOT))


def cancel_card(task_id: str, reason: str) -> None:
    if not reason.strip():
        raise FlowError("原因是空的：寫明為什麼作廢（例：見 D-009）")
    require_on_base()
    meta = load_meta(task_id)
    if meta.get("merged"):
        raise FlowError(f"{task_id} 已經合併，不能作廢")
    note = f"**派工單作廢**\n\n{reason.strip()}"
    if meta.get("pr"):
        run("gh", "pr", "close", str(meta["pr"]), "--comment", note, check=False)
    if meta.get("issue"):
        run("gh", "issue", "close", str(meta["issue"]), "--reason", "not planned", "--comment", note, check=False)
    if (ROOT / meta["worktree"]).exists():
        run("git", "worktree", "remove", "--force", meta["worktree"])
    run("git", "branch", "-D", meta["branch"], check=False)
    if has_remote():
        run("git", "push", "origin", "--delete", meta["branch"], check=False)
    meta["cancelled"] = True
    save_meta(meta)
    print(f"{task_id} 已作廢：issue、PR 已關閉，worktree 與分支已刪除")


def main() -> None:
    parser = argparse.ArgumentParser(description="派工單工具")
    parser.add_argument("action", choices=("new", "amend", "cancel"))
    parser.add_argument("task_id")
    parser.add_argument("--from", dest="sources", nargs="+", metavar="FILE", help="amend：用這些檔案的內容追加；- 代表 stdin")
    args = parser.parse_args()
    try:
        check_integrity()
        if args.sources and args.action != "amend":
            raise FlowError("--from 只能用在 amend")
        body = read_sources(args.sources) if args.sources else sys.stdin.read()
        if args.action == "new":
            new_card(args.task_id, body)
        elif args.action == "amend":
            amend_card(args.task_id, body)
        else:
            cancel_card(args.task_id, body)
    except FlowError as e:
        fail(str(e))


if __name__ == "__main__":
    main()
