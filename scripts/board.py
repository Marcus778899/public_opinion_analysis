"""布告欄（BOARD.md）維護工具，manager 透過它更新，避免手改造成格式亂掉。
布告欄只放「目前這一階段」；階段完成就整份封存，不設行數上限。

用法：
    board.py scope "<本輪目標>" "<不做>"
    board.py task set <task_id> <status> [--owner <agent>] [--evidence "<驗收證據>"]
    board.py decision add <D-編號> "<一行摘要>"     # 細節寫在 docs/decisions.md
    board.py blocker add|clear "<卡點>"
    board.py archive <tag>                          # 階段完成：BOARD.md → tasks/<tag>.md，派工單、meta、回報、證據 → tasks/<tag>/
    board.py check

archive：release.py finish 會自動做；版本以外的里程碑（主題）手動用，之後 docs.py commit。
新布告欄沿用「已定案決策」與「注意事項」（仍然有效），清空範圍與任務狀態。

status：todo / in-progress / qa / qa-fail / review / blocked / done（done = PR 已合併）
- done 必須附 --evidence
- 「嘗試」= pr.py 記錄的 qa 失敗次數（派工單的 meta），只是顯示；要不要找甲方由 pr.py 判斷（仲裁會退還次數，這裡不另外計）

exit code：0 成功；1 參數或格式錯誤
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone

from _common import REPORTS_DIR, ROOT, TASKS_DIR, FlowError, check_integrity

BOARD_PATH = ROOT / "BOARD.md"
ARCHIVE_TAG_RE = re.compile(r"^[A-Za-z0-9][\w.-]*$")
PREVIOUS_PREFIX = "> 上一階段："
STATUSES = ("todo", "in-progress", "qa", "qa-fail", "review", "blocked", "done")
DECISION_ID_RE = re.compile(r"^D-\d{3}$")
SECTIONS = {
    "scope": "## 目標與範圍",
    "decisions": "## 已定案決策（細節見 docs/decisions.md；要改先問甲方）",
    "tasks": "## 任務狀態",
    "blockers": "## 卡住／待甲方決定",
    "notes": "## 注意事項（踩過的坑）",
}
EMPTY_ITEM = "- （無）"


class BoardError(Exception):
    pass


def _read() -> list[str]:
    return BOARD_PATH.read_text(encoding="utf-8").splitlines()


def _commit(lines: list[str]) -> None:
    BOARD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _section_range(lines: list[str], key: str) -> tuple[int, int]:
    """回傳區塊內容的 [start, end)，不含標題行。"""
    heading = SECTIONS[key]
    if heading not in lines:
        raise BoardError(f"布告欄缺少區塊：{heading}")
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def _table_rows(lines: list[str], key: str) -> list[int]:
    """回傳表格所有行（含表頭與分隔線）的索引。"""
    start, end = _section_range(lines, key)
    rows = [i for i in range(start, end) if lines[i].startswith("|")]
    if len(rows) < 2:
        raise BoardError(f"{SECTIONS[key]} 的表格缺表頭")
    return rows


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]


def _cell(text: str) -> str:
    return text.replace("\n", " ").replace("|", "\\|").strip()


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def set_task(task_id: str, status: str, owner: str | None, evidence: str | None) -> int:
    """更新「任務狀態」表，回傳目前嘗試次數。"""
    if status not in STATUSES:
        raise BoardError(f"未知狀態 {status!r}，可用：{', '.join(STATUSES)}")
    if status == "done" and not evidence:
        raise BoardError("status=done 必須附 --evidence（實際驗證指令與結果）")

    lines = _read()
    rows = _table_rows(lines, "tasks")
    existing = next((i for i in rows[2:] if _split_row(lines[i])[0] == task_id), None)

    if existing is None:
        if not owner:
            raise BoardError(f"新任務 {task_id} 必須給 --owner")
        attempts, old_evidence = 0, ""
    else:
        _, old_owner, _, old_attempts, old_evidence = _split_row(lines[existing])
        owner = owner or old_owner
        attempts = int(old_attempts or 0)

    meta_path = TASKS_DIR / f"{task_id}.meta.json"
    if meta_path.is_file():
        attempts = json.loads(meta_path.read_text(encoding="utf-8")).get("qa_fails", 0)

    new_row = _row([
        _cell(task_id),
        _cell(owner),
        status,
        str(attempts),
        _cell(evidence) if evidence else old_evidence,
    ])
    if existing is None:
        lines.insert(rows[-1] + 1, new_row)
    else:
        lines[existing] = new_row
    _commit(lines)
    return attempts


def set_scope(goal: str, exclude: str) -> None:
    lines = _read()
    start, end = _section_range(lines, "scope")
    lines[start:end] = ["", f"- 本輪：{_cell(goal)}", f"- 不做：{_cell(exclude)}", ""]
    _commit(lines)


def add_decision(decision_id: str, summary: str) -> None:
    if not DECISION_ID_RE.match(decision_id):
        raise BoardError(f"決策編號格式要是 D-001，實際是 {decision_id!r}")
    lines = _read()
    rows = _table_rows(lines, "decisions")
    if any(_split_row(lines[i])[1] == decision_id for i in rows[2:]):
        raise BoardError(f"{decision_id} 已在布告欄上")
    today = datetime.now(timezone.utc).date().isoformat()
    lines.insert(rows[-1] + 1, _row([today, decision_id, _cell(summary)]))
    _commit(lines)


def update_blocker(text: str, clear: bool) -> None:
    lines = _read()
    start, end = _section_range(lines, "blockers")
    items = [i for i in range(start, end) if lines[i].startswith("- ")]
    target = f"- {_cell(text)}"

    if clear:
        if target not in (lines[i] for i in items):
            raise BoardError(f"找不到卡點：{text}")
        lines.remove(target)
        if len(items) == 1:
            lines.insert(items[0], EMPTY_ITEM)
    elif items and lines[items[0]] == EMPTY_ITEM:
        lines[items[0]] = target
    elif items:
        lines.insert(items[-1] + 1, target)
    else:
        lines.insert(start + 1, target)
    _commit(lines)


def archive(tag: str) -> None:
    """階段完成：整份布告欄封存成 tasks/<tag>.md，該階段的派工單、meta、回報與 qa／review／仲裁證據搬進 tasks/<tag>/。"""
    if not ARCHIVE_TAG_RE.match(tag):
        raise BoardError(f"封存名稱只能用英數、. _ -（例：v0.2.0），實際是 {tag!r}")
    board_copy = TASKS_DIR / f"{tag}.md"
    folder = TASKS_DIR / tag
    if board_copy.exists() or folder.exists():
        raise BoardError(f"{board_copy.relative_to(ROOT)} 或 {folder.relative_to(ROOT)}/ 已存在")
    metas = sorted(TASKS_DIR.glob("*.meta.json"))
    pending = []
    for path in metas:
        meta = json.loads(path.read_text(encoding="utf-8"))
        if not meta.get("merged") and not meta.get("cancelled"):
            pending.append(meta["task_id"])
    if pending:
        raise BoardError(f"還有沒合併的任務：{', '.join(pending)}；合併或 task.py cancel 後再封存")

    folder.mkdir(parents=True)
    for path in metas:
        task_id = path.name.removesuffix(".meta.json")
        for src, name in (
            (TASKS_DIR / f"{task_id}.md", f"{task_id}.md"),
            (path, path.name),
            (REPORTS_DIR / f"{task_id}.json", f"{task_id}.report.json"),
            *((REPORTS_DIR / f"{task_id}.{kind}.md", f"{task_id}.{kind}.md") for kind in ("qa", "review", "ruling")),
        ):
            if src.exists():
                shutil.move(src, folder / name)
    for path in TASKS_DIR.glob("release-*.json"):
        shutil.move(path, folder / path.name)
    # agent 用 Write 寫的回報常缺結尾換行，專案的 pre-commit（end-of-file-fixer）會改檔並中止封存提交：進 git 前先補
    for path in folder.iterdir():
        text = path.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            path.write_text(text + "\n", encoding="utf-8")
    (REPORTS_DIR / ".hook-blocks.json").unlink(missing_ok=True)

    lines = _read()
    board_copy.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 新階段：清空範圍與任務狀態；決策與踩過的坑仍然有效，留著
    start, end = _section_range(lines, "scope")
    lines[start:end] = ["", "- 本輪：（尚未設定）", "- 不做：（尚未設定）", ""]
    rows = _table_rows(lines, "tasks")
    del lines[rows[0] + 2:rows[-1] + 1]
    previous = f"{PREVIOUS_PREFIX}`tasks/{tag}.md`（派工單在 `tasks/{tag}/`）"
    existing = next((i for i, line in enumerate(lines) if line.startswith(PREVIOUS_PREFIX)), None)
    if existing is not None:
        lines[existing] = previous
    else:
        heading = SECTIONS["scope"]
        at = lines.index(heading)
        lines[at:at] = [previous, ""]
    _commit(lines)
    print(f"已封存：{board_copy.relative_to(ROOT)}、{folder.relative_to(ROOT)}/（{len(metas)} 張派工單）")


def check() -> list[str]:
    problems: list[str] = []
    lines = _read()
    for key, heading in SECTIONS.items():
        if heading not in lines:
            problems.append(f"缺少區塊：{heading}")
            continue
        if key != "tasks":
            continue
        for i in _table_rows(lines, "tasks")[2:]:
            cells = _split_row(lines[i])
            if len(cells) != 5:
                problems.append(f"第 {i + 1} 行欄位數不是 5：{lines[i]}")
                continue
            task_id, _, status, attempts, evidence = cells
            if status not in STATUSES:
                problems.append(f"{task_id}：未知狀態 {status!r}")
            if status == "done" and not evidence:
                problems.append(f"{task_id}：done 但沒有驗收證據")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="布告欄維護工具")
    sub = parser.add_subparsers(dest="area", required=True)

    task = sub.add_parser("task").add_subparsers(dest="action", required=True)
    task_set = task.add_parser("set")
    task_set.add_argument("task_id")
    task_set.add_argument("status", choices=STATUSES)
    task_set.add_argument("--owner")
    task_set.add_argument("--evidence")

    scope = sub.add_parser("scope")
    scope.add_argument("goal")
    scope.add_argument("exclude")

    decision = sub.add_parser("decision").add_subparsers(dest="action", required=True)
    decision_add = decision.add_parser("add")
    decision_add.add_argument("decision_id")
    decision_add.add_argument("summary")

    blocker = sub.add_parser("blocker")
    blocker.add_argument("action", choices=("add", "clear"))
    blocker.add_argument("text")

    sub.add_parser("archive").add_argument("tag")

    sub.add_parser("check")

    args = parser.parse_args()
    exit_code = 0
    try:
        check_integrity()
    except FlowError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        sys.exit(1)
    try:
        if args.area == "task":
            set_task(args.task_id, args.status, args.owner, args.evidence)
        elif args.area == "scope":
            set_scope(args.goal, args.exclude)
        elif args.area == "decision":
            add_decision(args.decision_id, args.summary)
        elif args.area == "blocker":
            update_blocker(args.text, args.action == "clear")
        elif args.area == "archive":
            archive(args.tag)
    except BoardError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        sys.exit(1)

    problems = check()
    for p in problems:
        print(f"布告欄問題：{p}", file=sys.stderr)
    if problems and exit_code == 0:
        exit_code = 1
    if exit_code == 0:
        print("OK")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
