"""專案初始化：git 分支結構、GitHub repo、.github workflows、labels、決策紀錄。只在新專案跑一次。

用法：
    init_project.py --repo <名稱> [--private]

做的事：
1. 沒有 git 就 git init（main）
2. 從 templates/ 放入 .github/workflows、docs/decisions.md；補齊 .gitignore
3. 第一個 commit；沒有 origin 就用 gh 建 repo（預設 public：Actions 免費不限分鐘數；private 在免費方案有每月分鐘上限）並 push
4. 從 main 開 develop、push，設為預設分支（PR 的 Closes #N 要合進預設分支才會關 issue）
5. 建立 labels
"""

import argparse
import shutil

from _common import BASE_BRANCH, BRANCH_TYPES, RELEASE_BRANCH, ROOT, FlowError, fail, has_remote, run

TEMPLATES = ROOT / "templates"
COPIES = {
    TEMPLATES / "github" / "workflows" / "ci.yml": ROOT / ".github" / "workflows" / "ci.yml",
    TEMPLATES / "github" / "workflows" / "sync_branch.yml": ROOT / ".github" / "workflows" / "sync_branch.yml",
    TEMPLATES / "decisions.md": ROOT / "docs" / "decisions.md",
}
GITIGNORE = (".env", ".worktrees/", "tasks/", "reports/", ".hooklog/", ".venv/", "node_modules/", "__pycache__/", "coverage-reports/")
EXTRA_LABELS = {"uat": "d93f0b", "backlog": "c5def5", "decision": "fbca04"}


def ensure_files() -> None:
    for src, dst in COPIES.items():
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
            print(f"建立 {dst.relative_to(ROOT)}")
    gitignore = ROOT / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [line for line in GITIGNORE if line not in existing]
    if missing:
        gitignore.write_text("\n".join(existing + missing) + "\n", encoding="utf-8")
        print(f".gitignore 補上：{' '.join(missing)}")


def ensure_git() -> None:
    if not (ROOT / ".git").exists():
        run("git", "init", "-b", RELEASE_BRANCH)
    has_commit = run("git", "rev-parse", "--verify", "HEAD", check=False) != ""
    run("git", "add", "-A")
    if run("git", "status", "--porcelain"):
        message = "chore: 初始化 agent 工作流程" if not has_commit else "chore: 加入 agent 工作流程"
        run("git", "commit", "-m", message)


def ensure_github(repo: str, private: bool) -> None:
    if not has_remote():
        visibility = "--private" if private else "--public"
        run("gh", "repo", "create", repo, visibility, "--source", ".", "--remote", "origin")
    if run("git", "branch", "--list", BASE_BRANCH) == "":
        run("git", "branch", BASE_BRANCH, RELEASE_BRANCH)
    # develop 先推：main 的 push 會觸發 sync_branch，那時 develop 必須已存在
    run("git", "push", "-u", "origin", BASE_BRANCH)
    run("git", "push", "-u", "origin", RELEASE_BRANCH)
    run("git", "checkout", BASE_BRANCH)
    run("gh", "repo", "edit", "--default-branch", BASE_BRANCH)
    for name in BRANCH_TYPES:
        run("gh", "label", "create", name, "--color", "0e8a16", "--force")
    for name, color in EXTRA_LABELS.items():
        run("gh", "label", "create", name, "--color", color, "--force")


def main() -> None:
    parser = argparse.ArgumentParser(description="專案初始化")
    parser.add_argument("--repo", required=True, help="GitHub repo 名稱")
    parser.add_argument("--private", action="store_true", help="預設 public")
    args = parser.parse_args()
    try:
        ensure_files()
        ensure_git()
        ensure_github(args.repo, args.private)
    except FlowError as e:
        fail(str(e))
    url = run("gh", "repo", "view", "--json", "url", "-q", ".url")
    print(f"完成：{url}（預設分支 {BASE_BRANCH}；主目錄已切到 {BASE_BRANCH}）")


if __name__ == "__main__":
    main()
