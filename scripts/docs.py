"""文件提交：布告欄、README、決策紀錄、UAT 報告、研究摘要、階段封存不走 PR，由 manager 直接 commit 到 develop。

用法：
    docs.py commit "<訊息>"     # 只提交 DOC_PATHS 內的修改與階段封存；其他修改不提交也不擋，只列出來

階段封存（board.py archive 產生的 tasks/<tag>.md 與 tasks/<tag>/）：tasks/ 在 .gitignore（進行中的派工單不進 git），
封存用 git add -f 強制加入。

程式碼的修改一律走派工單 → PR，不可用這支。

README 的 docker 指令要讓 agent 照抄就能跑：sandbox 例外只認單獨一行 `docker compose …`，
`make up` 這種包著 docker 的 target、或 `cd … && docker compose …`，甲方跑得起來、uat 跑不起來。
README 只經過這支進 git，所以在這裡擋。
"""

import argparse
import re

from _common import BASE_BRANCH, DOC_PATHS, ROOT, TASKS_DIR, FlowError, check_integrity, fail, has_remote, require_on_base, run, run_status
from guard_bash import DOCKER_WORD_RE, docker_misuse

CODE_RE = re.compile(r"```[^\n]*\n(.*?)```|`([^`\n]+)`", re.S)
MAKE_RE = re.compile(r"(?:^|[;&|(]\s*)make((?:\s+[^\s;&|)]+)*)")
VAR_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*[:?+!]?=\s*(.*)$")
RULE_RE = re.compile(r"^([^\s:=#][^:=]*?)\s*::?(?!=)\s*([^;]*)")
REF_RE = re.compile(r"\$[({]([A-Za-z_][A-Za-z0-9_]*)[)}]")


def parse_makefile() -> tuple[dict[str, list[str]], dict[str, list[str]], str | None]:
    """回傳（target → 相依 target、target → 展開變數後的指令、預設 target）。只看主目錄的 Makefile。"""
    path = ROOT / "Makefile"
    if not path.is_file():
        return {}, {}, None
    variables: dict[str, str] = {}
    deps: dict[str, list[str]] = {}
    recipes: dict[str, list[str]] = {}
    default = None
    current: list[str] = []
    # 先接起 \ 續行：recipe 的續行可以用空白縮排，逐行看會被當成新的一行，弄丟後面的指令
    for line in path.read_text(encoding="utf-8").replace("\\\n", " ").splitlines():
        if line.startswith("\t"):
            # 行首 @（不印指令）、-（忽略錯誤）、+ 是 make 的前綴，不是指令的一部分
            recipe = line.strip().lstrip("@-+").strip()
            if recipe and not recipe.startswith("#"):
                for t in current:
                    recipes[t].append(recipe)
            continue
        if m := VAR_RE.match(line):
            variables[m.group(1)] = m.group(2)
            current = []
        elif m := RULE_RE.match(line):
            current = [t for t in m.group(1).split() if not t.startswith(".")]
            for t in current:
                deps.setdefault(t, []).extend(m.group(2).split())
                recipes.setdefault(t, [])
            default = default or (current[0] if current else None)
        elif line.strip() and not line.startswith("#"):
            current = []

    def expand(text: str, depth: int = 0) -> str:
        if depth > 10:
            return text
        return REF_RE.sub(lambda m: "make" if m.group(1) == "MAKE" else expand(variables.get(m.group(1), ""), depth + 1), text)

    return deps, {t: [expand(r) for r in rs] for t, rs in recipes.items()}, default


def make_targets(args: str) -> list[str]:
    """make 後面的參數去掉 -s、-C 這類 flag 與 VAR=值，剩下的是 target。"""
    return [w for w in args.split() if not w.startswith("-") and "=" not in w]


def runs_docker(target: str, deps: dict[str, list[str]], recipes: dict[str, list[str]], seen: set[str]) -> bool:
    """target 本身、它的相依 target、或指令裡的 $(MAKE) x 有沒有呼叫 docker。"""
    if target in seen or target not in recipes:
        return False
    seen.add(target)
    for line in recipes[target]:
        if DOCKER_WORD_RE.search(line):
            return True
        for m in MAKE_RE.finditer(line):
            if any(runs_docker(t, deps, recipes, seen) for t in make_targets(m.group(1))):
                return True
    return any(runs_docker(t, deps, recipes, seen) for t in deps.get(target, []))


def readme_docker_problems() -> list[str]:
    """README 程式碼區塊裡，agent 照抄會在 sandbox 失敗的指令。"""
    readme = ROOT / "README.md"
    if not readme.is_file():
        return []
    deps, recipes, default = parse_makefile()
    problems = []
    for m in CODE_RE.finditer(readme.read_text(encoding="utf-8")):
        if m.group(2) and len(m.group(2).split()) < 2:
            continue  # 行內只有一個詞（`docker`、`docker-compose.yml`）是名詞提及，不是指令
        for line in (m.group(1) or m.group(2)).splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            if docker_misuse(line):
                problems.append(f"`{line}`：docker 要單獨一行 `docker compose …`，不跟 cd、&&、管線寫在一起")
                continue
            for mm in MAKE_RE.finditer(line):
                targets = make_targets(mm.group(1)) or [default]
                hit = [t for t in targets if t and runs_docker(t, deps, recipes, set())]
                if hit:
                    problems.append(f"`{line}`：Makefile 的 {'、'.join(hit)} 會跑 docker，寫成它展開後的 `docker compose …`（Makefile 可以留著給甲方自己用）")
    return problems


def changed_paths() -> list[str]:
    tracked = run("git", "diff", "HEAD", "--name-only").splitlines()
    untracked = run("git", "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(tracked + untracked))


def archive_paths() -> list[str]:
    """還沒提交的階段封存（未追蹤，或上次提交失敗留在暫存區）：有同名資料夾的 tasks/<tag>.md，連同 tasks/<tag>/。"""
    if not TASKS_DIR.is_dir():
        return []
    paths = []
    for folder in sorted(p for p in TASKS_DIR.iterdir() if p.is_dir()):
        board = TASKS_DIR / f"{folder.name}.md"
        if board.exists():
            paths += [board.relative_to(ROOT).as_posix(), folder.relative_to(ROOT).as_posix()]
    if not paths:
        return []
    untracked = run("git", "ls-files", "--others", "--", *paths)
    staged = run("git", "diff", "--cached", "--name-only", "--", *paths)
    return paths if untracked or staged else []


def commit(message: str) -> None:
    require_on_base()
    changed = changed_paths()
    paths = [p for p in changed if any(p == d or (d.endswith("/") and p.startswith(d)) for d in DOC_PATHS)]
    others = [p for p in changed if p not in paths]
    archives = archive_paths()
    if not paths and not archives:
        raise FlowError("沒有任何文件修改")
    if "README.md" in paths and (problems := readme_docker_problems()):
        raise FlowError(
            "README 的指令 agent 照抄會在 sandbox 裡失敗（uat 照 README 啟動服務），改完再提交：\n"
            + "\n".join(f"- {p}" for p in problems)
        )
    if has_remote():
        run("git", "pull", "--ff-only", "origin", BASE_BRANCH)

    def stage() -> None:
        if paths:
            run("git", "add", "--", *paths)
        if archives:
            run("git", "add", "-f", "--", *archives)

    stage()
    message = message.removeprefix("docs:").strip()
    commit_cmd = ("git", "commit", "-m", f"docs: {message}", "--", *paths, *archives)
    if run_status(*commit_cmd)[0] != 0:
        # 專案的 pre-commit hook 修了檔（檔尾換行、行尾空白…）會中止提交：加入修好的版本再提交一次，還失敗才是真的錯
        stage()
        run(*commit_cmd)
    paths += archives
    if has_remote():
        run("git", "push", "origin", BASE_BRANCH)
    print(f"已提交到 {BASE_BRANCH}：{'、'.join(paths)}")
    if others:
        print("主目錄另有非文件修改（沒提交）：" + "、".join(others) + "；下一次 pr.py open／merge 會擋，先依它的提示處理")


def main() -> None:
    parser = argparse.ArgumentParser(description="文件提交")
    parser.add_argument("action", choices=("commit",))
    parser.add_argument("message")
    args = parser.parse_args()
    try:
        check_integrity()
        commit(args.message)
    except FlowError as e:
        fail(str(e))


if __name__ == "__main__":
    main()
