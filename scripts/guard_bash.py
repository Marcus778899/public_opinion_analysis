"""PreToolUse hook（Bash）：依角色限制能跑的指令。

- 流程腳本（派工、PR、布告欄、發版）只有 manager 能跑；worker 自己跑 pr.py lock 就能把改過的測試洗白
- 派工單狀態檔（tasks/*.meta.json）只能由腳本改，任何角色都不可直接碰；manager 手改 qa_fails 就繞過了甲方的 unblock
沒有 agent_type（人直接開的 session）不限制。
這是比對指令字串的提醒，不是完整防線；範圍與驗收測試由 pr.py 用 git 檢查。

exit 0 = 放行；exit 2 = 擋下（stderr 回饋給 agent）
"""

import json
import re
import sys

FLOW_SCRIPT_RE = re.compile(r"\b(?:task|pr|board|docs|release|init_project)\.py\b")
STATE_FILE_RE = re.compile(r"\.meta\.json\b")


def main() -> None:
    payload = json.load(sys.stdin)
    agent = payload.get("agent_type")
    if agent is None:
        sys.exit(0)
    command = payload.get("tool_input", {}).get("command", "")
    if STATE_FILE_RE.search(command):
        print("派工單狀態檔（*.meta.json）只能由 scripts/ 的腳本讀寫；要看狀態用 board.py 或 gh pr view", file=sys.stderr)
        sys.exit(2)
    if agent != "manager" and FLOW_SCRIPT_RE.search(command):
        print(f"{agent} 不可執行流程腳本（task.py、pr.py、board.py…），那是 manager 的工作；做完就寫回報結束", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
