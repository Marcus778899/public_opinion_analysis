"""PreToolUse hook：依角色限制 Edit／Write 能碰的路徑。

hook 輸入的 agent_type：用 `claude --agent manager` 開的主 session 是 manager；subagent 是各自的角色。
沒有 agent_type（人直接開的 session）不限制。
派工單的「驗收測試」目錄：只有 qa 能寫，worker 不能改（qa 先寫測試、worker 再實作）。
注意：只擋 Edit／Write。Bash 寫檔由 sandbox 擋流程檔案（scripts/ 等），專案裡其他路徑擋不住；
這裡只是提早提醒，範圍的防線在 pr.py：open／merge 用 git diff 檢查範圍、比對驗收測試鎖定時的內容，不管用什麼方式寫的檔都會被抓到。

exit 0 = 放行；exit 2 = 擋下（stderr 回饋給 agent）
"""

import json
import sys
from pathlib import Path

from _common import path_allowed as is_allowed
from task import card_acceptance_paths

ROOT = Path(__file__).resolve().parent.parent

# 角色 → 允許寫入的路徑（檔案完全相符，或以 / 結尾的目錄前綴）
ALLOWED = {
    "manager": ("README.md", "docs/decisions.md"),
    "architect": (".worktrees/", "reports/", ".claude/agent-memory/architect/"),  # memory: project
    "researcher": ("docs/research/",),
    "uat": ("docs/uat/",),
    "security": ("docs/security/",),
    "designer": (".worktrees/", "reports/", ".claude/agent-memory/designer/"),  # memory: project
    "backend": (".worktrees/", "reports/"),
    "frontend": (".worktrees/", "reports/"),
    "qa": ("reports/",),  # 驗證證據 reports/<id>.qa.md；另外可寫派工單「驗收測試」列出的目錄，見 in_acceptance
}
WORKERS = ("designer", "backend", "frontend")


def in_acceptance(rel: str) -> bool:
    """rel 是否在某張派工單 worktree 的「驗收測試」目錄裡（.worktrees/<id>/<驗收測試路徑>）。"""
    parts = rel.split("/", 2)
    if len(parts) < 3 or parts[0] != ".worktrees":
        return False
    return is_allowed(parts[2], tuple(card_acceptance_paths(parts[1])))


def main() -> None:
    payload = json.load(sys.stdin)
    agent = payload.get("agent_type")
    if agent not in ALLOWED:
        sys.exit(0)
    file_path = payload.get("tool_input", {}).get("file_path") or payload.get("tool_input", {}).get("notebook_path")
    if not file_path:
        sys.exit(0)
    target = Path(file_path)
    if not target.is_absolute():
        target = Path(payload.get("cwd") or ROOT) / target
    try:
        rel = target.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel = None
    if rel is not None and agent in WORKERS and in_acceptance(rel):
        print(f"{agent} 不可修改驗收測試 {file_path}（qa 負責）；測試有問題就回報", file=sys.stderr)
        sys.exit(2)
    if rel is not None and (is_allowed(rel, ALLOWED[agent]) or (agent == "qa" and in_acceptance(rel))):
        sys.exit(0)
    allowed = "、".join(ALLOWED[agent]) + ("、派工單列出的驗收測試目錄" if agent == "qa" else "")
    print(f"{agent} 不可寫入 {file_path}；允許範圍：{allowed}。其他修改要交給負責的角色", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
