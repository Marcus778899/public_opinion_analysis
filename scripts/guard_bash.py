"""PreToolUse hook（Bash）：依角色限制能跑的指令。

- 流程腳本（派工、PR、布告欄、發版）只有 manager 能跑；worker 自己跑 pr.py lock 就能把改過的測試洗白
- 派工單狀態檔（tasks/*.meta.json）只能由腳本改，任何角色都不可直接碰；manager 手改 qa_fails 就繞過了甲方的 unblock
- docker 只能單獨下 `docker compose …`：sandbox 例外只認這個形式，跟 cd、&&、管線、重導向寫在一起
  或包進 bash -c 都會留在 sandbox 而失敗；先擋下並給正確寫法，不讓 agent 試錯繞路（所有 session 都檢查）
沒有 agent_type（人直接開的 session）不限制角色。
這是比對指令字串的提醒，不是完整防線；範圍與驗收測試由 pr.py 用 git 檢查。

exit 0 = 放行；exit 2 = 擋下（stderr 回饋給 agent）
"""

import json
import re
import shlex
import sys

FLOW_SCRIPT_RE = re.compile(r"\b(?:task|pr|board|docs|release|init_project)\.py\b")
STATE_FILE_RE = re.compile(r"\.meta\.json\b")
SHELLS = {"bash", "sh", "zsh"}
# 後面接另一個指令的包裝：timeout 600 docker compose … 一樣留在 sandbox
WRAPPERS = {"env", "time", "timeout", "nohup", "xargs", "sudo", "exec", "command", "watch"}
KEYWORDS = {"do", "then", "else", "elif", "if", "while", "until", "!", "{"}
HEREDOC_RE =re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?=\n|$)", re.S)
DOCKER_HINT = (
    "docker 只能單獨下一行 `docker compose …`（sandbox 例外只認這個形式），例："
    "docker compose --env-file .env -f .worktrees/<task_id>/compose.yaml run --rm test。"
    "不要 cd（用 -f 指定 compose 檔）、不要接 &&、;、|、> 或 2>&1（輸出會直接回給你；嫌長就讓 test 服務的指令自己精簡，例 pytest -q）、"
    "不要包進 bash -c 或 script；只有 docker compose 能用，docker run、docker-compose 都不行"
)


def docker_misuse(command: str) -> bool:
    """指令裡有 docker，但不是單獨一個 `docker compose …`。

    用 shlex 切詞：引號裡的字（例 commit 訊息寫到 docker）不算指令；heredoc 內文（例 qa 寫證據檔）先拿掉。
    換行等同 `;`。切不開（引號不成對）就不判斷，交給 sandbox。
    """
    command = HEREDOC_RE.sub("<< HEREDOC\n", command)
    command = command.replace("\\\n", " ").replace("\n", " ; ")
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    has_operator = any(t and all(c in "();<>|&" for c in t) for t in tokens)
    segments: list[list[str]] = [[]]
    for t in tokens:
        if t and all(c in "();<>|&" for c in t):
            segments.append([])
        else:
            segments[-1].append(t)
    for seg in segments:
        words = [w for w in seg if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w)]
        while words and words[0] in KEYWORDS:
            words.pop(0)
        if not words:
            continue
        cmd = words[0].rsplit("/", 1)[-1]
        if cmd in SHELLS and any(re.search(r"\bdocker\b", w) for w in words[1:]):
            return True
        if cmd in WRAPPERS and any(w.rsplit("/", 1)[-1].startswith("docker") for w in words[1:]):
            return True
        if cmd.startswith("docker"):
            ok = cmd == "docker" and words[1:2] == ["compose"] and len(words) == len(seg)
            if not ok or has_operator:
                return True
    return False


def main() -> None:
    payload = json.load(sys.stdin)
    agent = payload.get("agent_type")
    command = payload.get("tool_input", {}).get("command", "")
    if docker_misuse(command):
        print(DOCKER_HINT, file=sys.stderr)
        sys.exit(2)
    if agent is None:
        sys.exit(0)
    if STATE_FILE_RE.search(command):
        print("派工單狀態檔（*.meta.json）只能由 scripts/ 的腳本讀寫；要看狀態用 board.py 或 gh pr view", file=sys.stderr)
        sys.exit(2)
    if agent != "manager" and FLOW_SCRIPT_RE.search(command):
        print(f"{agent} 不可執行流程腳本（task.py、pr.py、board.py…），那是 manager 的工作；做完就寫回報結束", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
