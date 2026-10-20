"""腳本共用：路徑、git／gh 呼叫、派工單 meta。"""

import fnmatch
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "tasks"
REPORTS_DIR = ROOT / "reports"
WORKTREES_DIR = ROOT / ".worktrees"
BASE_BRANCH = "develop"
RELEASE_BRANCH = "main"
BRANCH_TYPES = ("feat", "fix", "chore", "docs", "refactor", "test")
# 相依清單與 lock 檔（fnmatch，* 也比對 /）：改到就要重裝環境；pr.py 的 fast 通道也把它們當受保護路徑
DEP_PATTERNS = (
    "*package.json", "*package-lock.json", "*pnpm-lock.yaml", "*.lock",  # Node（yarn.lock、poetry.lock、uv.lock 也在 *.lock）
    "*requirements*.txt", "*pyproject.toml", "*Pipfile",  # Python
    "*pom.xml", "*build.gradle", "*build.gradle.kts", "*gradle.lockfile", "*libs.versions.toml",  # Java
    "*go.mod", "*go.sum",  # Go
)
# 流程本身（關卡程式、hook、權限、契約、共用規範）：主目錄裡被改過就停止一切流程，只有甲方能還原
PROTECTED_PATHS = ("scripts", ".claude", "contracts", "CLAUDE.md")
# 會正常變動的：角色記憶（memory: project）、甲方在確認視窗按「不再詢問」產生的本機設定
INTEGRITY_IGNORE = (".claude/agent-memory/", ".claude/settings.local.json")
# 測試檔（fnmatch）：fast 通道要求附測試、CI 覆蓋率檢查不把測試檔算成「改到的程式」
TEST_PATTERNS = ("*/tests/*", "tests/*", "*/test/*", "test/*", "*/__tests__/*", "*test_*.py", "*_test.*", "*.test.*", "*.spec.*")
# 主目錄裡可以有未提交修改的：manager 寫的文件（docs.py commit 提交）
DOC_PATHS = ("BOARD.md", "README.md", "docs/decisions.md", "docs/uat/", "docs/research/", "docs/security/")
# 主目錄環境（make setup）對應的相依雜湊；worktree 用 symlink 共用主目錄的環境
DEPS_STAMP = WORKTREES_DIR / ".deps-stamp"


class FlowError(Exception):
    pass


def run(*cmd: str, cwd: Path = ROOT, check: bool = True, input: str | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, input=input)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise FlowError(f"`{' '.join(cmd)}` 失敗：{detail}")
    return result.stdout.strip()


def run_status(*cmd: str, cwd: Path = ROOT) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr).strip()


def path_allowed(rel: str, rules: tuple[str, ...] | list[str]) -> bool:
    """rel 是否符合規則：檔案完全相符，或以 / 結尾的目錄前綴。"""
    return any(rel == r or (r.endswith("/") and rel.startswith(r)) for r in rules)


def is_dep_file(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in DEP_PATTERNS)


def deps_hash(ref: str = "HEAD") -> str:
    """ref 上所有相依檔的內容雜湊；沒有相依檔回傳空字串。"""
    lines = [line for line in run("git", "ls-tree", "-r", ref).splitlines() if is_dep_file(line.split("\t", 1)[1])]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest() if lines else ""


def check_integrity() -> None:
    """主目錄的流程檔案和 git 紀錄不同就拒絕：守衛程式被改了，後面的檢查都不可信。
    預防靠 sandbox（Bash 寫不進這些路徑）；這是第二道，事後偵測。沒有 sandbox 的原生 Windows 只剩這道，
    而且連這個檢查一起改掉就擋不住。範本更新走 update.sh，它會直接 commit，不會觸發。"""
    code, out = run_status("git", "status", "--porcelain", "--untracked-files=all", "--", *PROTECTED_PATHS)
    if code != 0:
        return  # 還不是 git repo（初始化之前）
    changed = [line.split(None, 1)[1] for line in out.splitlines() if line.strip()]
    changed = [f for f in changed if not path_allowed(f, INTEGRITY_IGNORE)]
    # 改完直接 commit 到主目錄也算：正常的修改都經過 PR 或 docs.py／update.sh（都會 push），agent 不能 push
    if has_remote() and run_status("git", "rev-parse", "--verify", f"origin/{BASE_BRANCH}")[0] == 0:
        excludes = [f":(exclude){p}" for p in INTEGRITY_IGNORE]
        local = run("git", "diff", "--name-only", f"origin/{BASE_BRANCH}...HEAD", "--", *PROTECTED_PATHS, *excludes)
        changed += [f"{f}（本機 commit 未 push）" for f in local.splitlines()]
    if changed:
        raise FlowError(
            "流程檔案在主目錄被改過，所有流程停止：" + "、".join(changed)
            + "。這不是 agent 能處理的：回報甲方，請甲方看 `git diff` 確認——不是自己改的就還原（`git checkout -- <檔案>`），"
            "是甲方自己改的就自己 commit；agent 不可自行還原、commit 或繞過"
        )


def check_main_clean() -> None:
    """主目錄只能有文件的未提交修改。其他的多半是 worker 忘了 cd 到 worktree、在主目錄跑了指令（例 npm install）；
    當場抓，弄髒的幾乎一定是剛做完的那張單，不要拖到 release.py 才爆、沒人記得是誰。流程檔案由 check_integrity 管。"""
    tracked = run("git", "diff", "HEAD", "--name-only").splitlines()
    untracked = run("git", "ls-files", "--others", "--exclude-standard").splitlines()
    stray = sorted(
        p for p in set(tracked + untracked)
        if not path_allowed(p, DOC_PATHS) and not path_allowed(p, INTEGRITY_IGNORE)
        and not any(p == d or p.startswith(d + "/") for d in PROTECTED_PATHS)
    )
    if stray:
        raise FlowError(
            "主目錄有不該出現的修改：" + "、".join(stray[:20]) + ("…" if len(stray) > 20 else "")
            + "。多半是剛做完的 worker 在主目錄（不是 .worktrees/<id>）跑了指令：派那個 worker 把需要的修改搬到自己的 worktree，"
            "主目錄的用 `git restore <檔案>` 還原、多出來的檔案刪掉；manager 不要自己刪，看不出是誰的就問甲方"
        )


def has_remote() -> bool:
    return "origin" in run("git", "remote", check=False).split()


def current_branch(cwd: Path = ROOT) -> str:
    return run("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)


def require_on_base() -> None:
    branch = current_branch()
    if branch != BASE_BRANCH:
        raise FlowError(f"主目錄必須停在 {BASE_BRANCH}，目前在 {branch}；功能開發一律在 .worktrees/ 裡做")


def number_from_url(url: str) -> int:
    return int(url.strip().rstrip("/").rsplit("/", 1)[1])


def meta_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.meta.json"


def load_meta(task_id: str) -> dict:
    path = meta_path(task_id)
    if not path.exists():
        raise FlowError(f"找不到 {path.relative_to(ROOT)}；先用 task.py new 建立派工單")
    return json.loads(path.read_text(encoding="utf-8"))


def save_meta(meta: dict) -> None:
    TASKS_DIR.mkdir(exist_ok=True)
    meta_path(meta["task_id"]).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fail(message: str, code: int = 1) -> None:
    print(f"錯誤：{message}", file=sys.stderr)
    sys.exit(code)
