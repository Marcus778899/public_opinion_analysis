"""文件提交：布告欄、README、決策紀錄、UAT 報告、研究摘要、階段封存不走 PR，由 manager 直接 commit 到 develop。

用法：
    docs.py commit "<訊息>"     # 只提交 DOC_PATHS 內的修改與階段封存；其他修改不提交也不擋，只列出來

階段封存（board.py archive 產生的 tasks/<tag>.md 與 tasks/<tag>/）：tasks/ 在 .gitignore（進行中的派工單不進 git），
封存用 git add -f 強制加入。

程式碼的修改一律走派工單 → PR，不可用這支。
"""

import argparse

from _common import BASE_BRANCH, DOC_PATHS, ROOT, TASKS_DIR, FlowError, check_integrity, fail, has_remote, require_on_base, run


def changed_paths() -> list[str]:
    tracked = run("git", "diff", "HEAD", "--name-only").splitlines()
    untracked = run("git", "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(tracked + untracked))


def archive_paths() -> list[str]:
    """還沒進 git 的階段封存：有同名資料夾的 tasks/<tag>.md，連同 tasks/<tag>/。"""
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
    return paths if untracked else []


def commit(message: str) -> None:
    require_on_base()
    changed = changed_paths()
    paths = [p for p in changed if any(p == d or (d.endswith("/") and p.startswith(d)) for d in DOC_PATHS)]
    others = [p for p in changed if p not in paths]
    archives = archive_paths()
    if not paths and not archives:
        raise FlowError("沒有任何文件修改")
    if has_remote():
        run("git", "pull", "--ff-only", "origin", BASE_BRANCH)
    if paths:
        run("git", "add", "--", *paths)
    if archives:
        run("git", "add", "-f", "--", *archives)
    paths += archives
    message = message.removeprefix("docs:").strip()
    run("git", "commit", "-m", f"docs: {message}", "--", *paths)
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
