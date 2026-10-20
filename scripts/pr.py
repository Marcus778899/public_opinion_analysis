"""PR 工具：manager 透過它開 PR、記錄 qa／review 結果、合併。合併條件由程式把關，不靠 prompt。

用法：
    pr.py lock <task_id>                          # qa 寫完驗收測試後鎖定（記下這張單對驗收測試的改動）；qa 補測試後要重新鎖
    pr.py open <task_id>                          # 檢查範圍與驗收測試鎖、回報 → push 分支 → 開 PR 到 develop（已有 PR 就只 push）
    pr.py record <task_id> qa                     # 讀 reports/<id>.qa.md，記錄 qa 結果並留言到 PR
    pr.py record <task_id> review                 # 讀 reports/<id>.review.md，記錄 architect code review（實作類任務）
    pr.py ruling <task_id>                        # 讀 reports/<id>.ruling.md，記錄 architect 對驗收測試的仲裁
    pr.py approve <task_id>...            < 內容   # 甲方核可（設計類任務，可一次多張）；settings 的 ask 讓它一定跳確認，按允許就是核可
    pr.py unblock <task_id>               < 內容   # qa FAIL 或仲裁次數達上限後，甲方決定繼續；同樣一定跳確認
    pr.py sync <task_id>                          # 把 develop 最新的合併併進分支；任務本身的 diff 沒變就沿用 qa／review，否則重驗
    pr.py merge <task_id>                         # 分支已含最新 develop + qa PASS + review APPROVE（fast 通道免 review）（都對應目前的 commit）+ CI 綠（含改到的程式碼覆蓋率，見 coverage_gate.py）→ merge commit 合併（保留分支歷史）、清掉 worktree 與本機分支；遠端分支保留供追蹤

qa／review 綁定 commit：之後再 push 新 commit，就要重新驗證與審查。
qa／review 的結果由程式從證據檔讀，不由 manager 轉述（manager 不會把 FAIL 記成 PASS，也不用把證據再打一次）：
- 證據檔第一行是「<結論> <commit 前 7 碼>」：qa 寫 PASS／FAIL，architect 寫 APPROVE／REQUEST_CHANGES
- commit 必須是分支目前的 HEAD，避免拿上一輪的結論來記；之後內容整份留言到 PR
範圍與驗收測試由程式檢查（open、merge 都會查，不靠 qa 看 diff）：
- 分支改到的檔案必須在派工單「負責檔案」或「驗收測試」裡
- 有「驗收測試」的單要先 lock；之後驗收測試內容跟鎖定時不同就拒絕（worker 改測試讓自己過）
- 鎖的是「這張單對驗收測試目錄的改動」（patch-id），不是整個目錄：別張單合併進 develop 的測試不會讓鎖失效；
  sync 乾淨合併時鎖跟著移到新 commit（是 git 合的，不是 worker 改的），有衝突由 worker 解的就要 qa 確認後重新 lock
甲方關卡由程式把關（auto 模式下 prompt 擋不住）：
- 設計類任務（architect／designer 負責、類型 docs）的 review 只能用 approve，merge 會檢查；fix、chore 等走 architect review
- qa FAIL 達 MAX_QA_FAILS 次後 open 拒絕，要甲方 unblock
fast 通道（派工單「通道」欄位）：免 architect review、免先寫驗收測試；範圍、qa 驗證、CI 照舊。
open、merge 檢查 diff，超過 FAST_MAX_FILES 個檔、FAST_MAX_LINES 行，或碰到 FAST_PROTECTED，就自動升級成 full（不可降級），merge 前要 review。
覆蓋率在 CI 檢查（scripts/coverage_gate.py：這次改到的程式碼至少 80% 有測試），merge 要求 CI 綠就涵蓋；
不在本機量：全量測試跑兩次會超過 Bash 時限、本機共用 .env 的 DB 會互撞，而且 CI 的結果 agent 碰不到。
一次合併一張，合併的就是驗過的：merge 要求分支已包含最新的 develop，否則先 sync。
sync 在 worktree 把 develop 併進來：乾淨合併且任務 diff 不變（patch-id 相同）→ qa／review 沿用到新 commit，只等 CI；
diff 變了 → 重新 qa、review；有衝突 → 留在衝突狀態，派原 worker 解完 commit，再走 open → qa → review。
測試本身可能寫錯，仲裁由 architect 依契約判定（不等撞到上限才找甲方）：
- worker 回報 disputes（測試與契約矛盾），或 qa FAIL 達 RULING_AT_FAILS 次 → open 要求先有這個 FAIL 次數之後的仲裁
- 仲裁 TEST_WRONG：那次 FAIL 不算 worker 的，退還 1 次，每張單最多 MAX_REFUNDS 次；迴圈仍有上限，最壞情況多跑一輪就找甲方
- 每張單最多仲裁 MAX_RULINGS 次：disputes 可能發生在開 PR 之前，qa 失敗次數管不到「申訴 → TEST_OK → 再申訴」的迴圈；
  還需要仲裁就停下來問甲方（unblock 一併歸零）
exit code：0 成功；1 條件不符或指令失敗
"""

import argparse
import fnmatch
import hashlib
import json
import sys
from pathlib import Path

from _common import (
    BASE_BRANCH,
    REPORTS_DIR,
    TEST_PATTERNS,
    ROOT,
    DEP_PATTERNS,
    FlowError,
    check_integrity,
    check_main_clean,
    fail,
    has_remote,
    is_dep_file,
    load_meta,
    number_from_url,
    path_allowed,
    run,
    run_status,
    save_meta,
)
from task import card_paths
from validate_report import ReportError, check_consistency, check_schema, load_report

# 證據檔第一行的結論 → 記錄的結果
VERDICTS = {
    "qa": {"PASS": "pass", "FAIL": "fail"},
    "review": {"APPROVE": "approve", "REQUEST_CHANGES": "changes"},
    "ruling": {"TEST_WRONG": "test_wrong", "TEST_OK": "test_ok"},
}
LABELS = {"qa": "QA", "review": "Code review（architect）", "ruling": "驗收測試仲裁（architect）"}
GATED_OWNERS = ("architect", "designer")
GATED_KIND = "docs"
MAX_QA_FAILS = 3
RULING_AT_FAILS = 2
MAX_REFUNDS = 1
MAX_RULINGS = 2
FAST_MAX_FILES = 5
FAST_MAX_LINES = 100
# 碰到就要 architect review：資料、契約、權限、依賴、CI 與建置、流程本身（fnmatch，* 也比對 /；誤判只會讓它升級，不會放水）
FAST_PROTECTED = (
    "*migration*", "*contracts/*", "*auth*", "*permission*", "*security*",
    *DEP_PATTERNS,
    ".github/*", "*Makefile", "*.env.example",
    # compose 指令在 sandbox 外執行（甲方允許的例外），compose 檔與 Dockerfile 等於能碰整台電腦
    "*Dockerfile*", "*compose*.yml", "*compose*.yaml",
    "scripts/*", ".claude/*", "CLAUDE.md",
    # 覆蓋率設定：排除檔案就能繞過 CI 的覆蓋率檢查（pyproject.toml、pom.xml、build.gradle 已在 DEP_PATTERNS）
    "*.coveragerc", "*vitest.config*", "*jest.config*", "*.nycrc*", ".coverage-exempt",
    # CI 資安稽核的忽略清單：加一條忽略就等於放行一個漏洞
    "*osv-scanner.toml", "*.gitleaks.toml", "*.gitleaksignore", "*.semgrepignore",
)
# fast 單要附測試：diff 裡至少有一個符合的檔（docs 類免）


def needs_client_approval(meta: dict) -> bool:
    """甲方只核可設計與決策：architect／designer 負責的 docs 類任務（設計、契約、畫面、技術棧）。"""
    return meta["owner"] in GATED_OWNERS and meta["kind"] == GATED_KIND


def head_sha(meta: dict) -> str:
    return run("git", "rev-parse", meta["branch"])


def acceptance_patch(meta: dict, paths: list[str]) -> str:
    """這張單對驗收測試目錄的改動（patch-id，不含行號）；空字串表示這張單沒有加或改任何驗收測試。"""
    diff = run("git", "diff", "--no-renames", f"{BASE_BRANCH}...{meta['branch']}", "--", *paths)
    return run("git", "patch-id", "--stable", input=diff + "\n").split(" ")[0] if diff else ""


def acceptance_tree_hash(meta: dict, paths: list[str]) -> str:
    """舊版的鎖（整個目錄的內容雜湊）：只用來讀更新前鎖的單。"""
    tree = run("git", "ls-tree", "-r", meta["branch"], "--", *paths)
    return hashlib.sha256(tree.encode()).hexdigest() if tree else ""


def acceptance_unchanged(meta: dict, paths: list[str]) -> bool:
    lock = meta["acceptance_lock"]
    if "patch" not in lock:
        # 舊版的鎖：內容跟鎖定時一樣就換成新格式；不一樣（多半是別張單的測試合併進來）就要重新 lock
        if acceptance_tree_hash(meta, paths) != lock["hash"]:
            return False
        meta["acceptance_lock"] = {"patch": acceptance_patch(meta, paths), "sha": lock["sha"]}
        save_meta(meta)
        return True
    return acceptance_patch(meta, paths) == lock["patch"]


def check_scope(meta: dict) -> None:
    """分支改到的檔案（含刪除、改名）都要在「負責檔案」或「驗收測試」裡；驗收測試要跟鎖定時一樣。"""
    task_id = meta["task_id"]
    acceptance = card_paths(task_id, "驗收測試")
    allowed = card_paths(task_id, "負責檔案") + acceptance
    changed = run("git", "diff", "--name-only", "--no-renames", f"{BASE_BRANCH}...{meta['branch']}").splitlines()
    outside = [f for f in changed if not path_allowed(f, allowed)]
    if outside:
        raise FlowError(
            "改到派工單範圍以外的檔案：" + "、".join(outside)
            + "；請 worker 還原（範圍真的不夠就在回報的 open_questions 說明，由 manager 決定）"
        )
    if not acceptance:
        return
    lock = meta.get("acceptance_lock")
    if not lock:
        raise FlowError(f"驗收測試還沒鎖定：qa 寫完測試、確認失敗原因正確後執行 pr.py lock {task_id}")
    if not acceptance_unchanged(meta, acceptance):
        raise FlowError(
            f"驗收測試跟鎖定時（commit {lock['sha'][:7]}）不一樣：worker 不可改測試，請還原；"
            "測試本身有錯就回報，由 qa 修正後重新 pr.py lock；"
            "如果是 sync 解衝突時動到驗收測試，派 qa 確認測試沒被改壞後重新 pr.py lock"
        )


def rulings_exhausted(meta: dict, why: str) -> FlowError:
    task_id = meta["task_id"]
    return FlowError(
        f"{task_id} {why}，但已仲裁 {meta.get('rulings', 0)} 次（上限 {MAX_RULINGS}）：停下來，把卡點與選項開成 D-編號問甲方；"
        f"甲方決定繼續後執行 pr.py unblock {task_id}；證據：{evidence_list(task_id)}"
    )


def require_ruling(meta: dict) -> None:
    """qa FAIL 達 RULING_AT_FAILS 次後，要有這個次數之後的仲裁；lock（重派 worker 前）與 open 都查。"""
    fails = meta.get("qa_fails", 0)
    ruling = meta.get("ruling")
    if fails >= RULING_AT_FAILS and not (ruling and ruling["after_fails"] == fails):
        if meta.get("rulings", 0) >= MAX_RULINGS:
            raise rulings_exhausted(meta, f"qa 已 FAIL {fails} 次需要仲裁")
        raise FlowError(
            f"{meta['task_id']} qa 已 FAIL {fails} 次：先派 architect 依契約審驗收測試，結果寫 "
            f"reports/{meta['task_id']}.ruling.md，再 pr.py ruling {meta['task_id']}"
        )


def fast_lane_problems(meta: dict) -> list[str]:
    numstat = run("git", "diff", "--numstat", "--no-renames", f"{BASE_BRANCH}...{meta['branch']}").splitlines()
    files = [line.split("\t", 2) for line in numstat if line]
    problems = []
    if len(files) > FAST_MAX_FILES:
        problems.append(f"改了 {len(files)} 個檔（上限 {FAST_MAX_FILES}）")
    lines = sum(int(a) + int(d) for a, d, _ in files if a != "-")
    if lines > FAST_MAX_LINES:
        problems.append(f"改了 {lines} 行（上限 {FAST_MAX_LINES}）")
    protected = [p for _, _, p in files if any(fnmatch.fnmatch(p, pat) for pat in FAST_PROTECTED)]
    if protected:
        problems.append("碰到受保護路徑 " + "、".join(protected))
    if meta["kind"] != "docs" and not any(fnmatch.fnmatch(p, pat) for _, _, p in files for pat in TEST_PATTERNS):
        problems.append("沒有附任何測試檔")
    return problems


def check_lane(meta: dict) -> None:
    """fast 通道超出條件就升級成 full；只升不降，升級後 merge 要 architect review。"""
    if meta.get("lane") != "fast":
        return
    problems = fast_lane_problems(meta)
    if not problems:
        return
    meta["lane"] = "full"
    meta["lane_upgraded"] = problems
    save_meta(meta)
    message = "；".join(problems)
    comment(meta, f"**通道自動升級 fast → full**：{message}；合併前需要 architect review")
    print(f"{meta['task_id']} 通道升級為 full（{message}）：qa 之後要派 architect review", file=sys.stderr)


def lock(task_id: str) -> None:
    meta = load_meta(task_id)
    require_ruling(meta)
    acceptance = card_paths(task_id, "驗收測試")
    if not acceptance:
        raise FlowError(f"{task_id} 的派工單沒有「驗收測試」目錄，不需要鎖定")
    patch = acceptance_patch(meta, acceptance)
    if not patch:
        raise FlowError(f"{meta['branch']} 還沒有加或改任何驗收測試：先派 qa「A. 寫驗收測試」並 commit")
    sha = head_sha(meta)
    meta["acceptance_lock"] = {"patch": patch, "sha": sha}
    save_meta(meta)
    print(f"{task_id} 驗收測試已鎖定 @ {sha[:7]}")


def open_pr(task_id: str) -> None:
    meta = load_meta(task_id)
    fails = meta.get("qa_fails", 0)
    if fails >= MAX_QA_FAILS:
        raise FlowError(
            f"{task_id} qa 已 FAIL {fails} 次：停下來，把卡點與選項開成 D-編號問甲方；"
            f"甲方決定繼續後執行 pr.py unblock {task_id}；證據：{evidence_list(task_id)}"
        )
    require_ruling(meta)
    worktree = ROOT / meta["worktree"]
    if run("git", "status", "--porcelain", cwd=worktree):
        raise FlowError(f"{meta['worktree']} 還有沒 commit 的修改，請 worker 先 commit")
    check_main_clean()
    ahead = int(run("git", "rev-list", "--count", f"{BASE_BRANCH}..{meta['branch']}"))
    if ahead == 0:
        raise FlowError(f"{meta['branch']} 沒有任何新 commit")
    check_scope(meta)
    check_lane(meta)

    report_path = REPORTS_DIR / f"{task_id}.json"
    try:
        report = load_report(report_path)
        errors = check_schema(report) or check_consistency(report, report_path)
    except ReportError as e:
        errors = [str(e)]
    if errors:
        raise FlowError("回報不合格：" + "；".join(errors))
    if report.get("disputes"):
        if meta.get("rulings", 0) >= MAX_RULINGS:
            raise rulings_exhausted(meta, "worker 又認為驗收測試與契約矛盾")
        raise FlowError(
            f"worker 認為驗收測試與契約矛盾（{len(report['disputes'])} 項，見 {report_path.relative_to(ROOT)} 的 disputes）："
            f"派 architect 仲裁，結果寫 reports/{task_id}.ruling.md，再 pr.py ruling {task_id}"
        )
    if report["status"] != "done":
        raise FlowError(f"回報狀態是 {report['status']}，不是 done")

    # 不加 -u：會寫 .git/config，sandbox 裡被擋；之後的 push 都明寫 origin 與分支，不需要 upstream
    run("git", "push", "origin", meta["branch"], cwd=worktree)
    if meta.get("pr"):
        print(f"已更新 PR #{meta['pr']}（新 commit 需要重新 qa 與 review）")
        return

    verification = report["verification"]
    closes = f"Closes #{meta['issue']}\n\n" if meta.get("issue") else ""
    body = (
        f"{closes}派工單：`tasks/{task_id}.md`（負責：{meta['owner']}）\n\n"
        f"Worker 自驗：`{verification['command']}` → exit {verification['exit_code']}\n\n"
        "變更檔案：\n" + "\n".join(f"- `{f}`" for f in report["files_changed"])
    )
    url = run(
        "gh", "pr", "create", "--base", BASE_BRANCH, "--head", meta["branch"],
        "--title", f"{meta['kind']}({task_id}): {meta['title']}", "--body", body,
    )
    meta["pr"] = number_from_url(url)
    save_meta(meta)
    print(f"PR #{meta['pr']}：{url}")


def evidence_path(task_id: str, kind: str) -> Path:
    return REPORTS_DIR / f"{task_id}.{kind}.md"


def read_verdict(task_id: str, kind: str, sha: str) -> tuple[str, str]:
    """從證據檔讀出 (結果, 內容)；格式不對、commit 不是目前 HEAD 就拒絕。"""
    path = evidence_path(task_id, kind)
    rel = path.relative_to(ROOT)
    who = "qa" if kind == "qa" else "architect"
    redo = {"qa": "重新 qa", "review": "重新 review", "ruling": "重新仲裁"}[kind]
    if not path.is_file():
        raise FlowError(f"找不到 {rel}：{who} 要把結論與證據寫在這個檔")
    text = path.read_text(encoding="utf-8").strip()
    first, _, rest = text.partition("\n")
    words = first.split()
    verdicts = VERDICTS[kind]
    if len(words) != 2 or words[0] not in verdicts:
        raise FlowError(f"{rel} 第一行必須是「{'／'.join(verdicts)} <commit 前 7 碼>」，實際是「{first}」")
    if len(words[1]) < 7 or not sha.startswith(words[1]):
        raise FlowError(f"{rel} 驗的是 commit {words[1]}，分支目前是 {sha[:7]}：要{redo}")
    if not rest.strip():
        raise FlowError(f"{rel} 只有結論沒有證據：qa 要附實際執行輸出，review／仲裁要附檢查結果與依據")
    return verdicts[words[0]], text


def evidence_list(task_id: str) -> str:
    paths = [evidence_path(task_id, k) for k in VERDICTS] + [REPORTS_DIR / f"{task_id}.json"]
    return "、".join(str(p.relative_to(ROOT)) for p in paths if p.is_file()) or "（無）"


def ruling(task_id: str) -> None:
    """architect 依契約判定驗收測試對不對。TEST_WRONG 退還 1 次 FAIL（有上限）；之後由 qa 依仲裁修測試、重新 lock。"""
    meta = load_meta(task_id)
    if meta.get("rulings", 0) >= MAX_RULINGS:
        raise rulings_exhausted(meta, "要再仲裁一次")
    sha = head_sha(meta)
    result, body = read_verdict(task_id, "ruling", sha)
    meta["rulings"] = meta.get("rulings", 0) + 1
    note = f"（第 {meta['rulings']} 次仲裁，上限 {MAX_RULINGS}）"
    if result == "test_wrong" and meta.get("qa_fails", 0) > 0:
        if meta.get("refunds", 0) < MAX_REFUNDS:
            meta["qa_fails"] -= 1
            meta["refunds"] = meta.get("refunds", 0) + 1
            note += f"；退還 1 次 FAIL，目前 {meta['qa_fails']} 次"
        else:
            note += f"；退還次數已用完（每張單 {MAX_REFUNDS} 次），FAIL 次數不變"
    meta["ruling"] = {"result": result, "sha": sha, "after_fails": meta.get("qa_fails", 0)}
    save_meta(meta)
    comment(meta, f"**{LABELS['ruling']}：{result.upper()}**（commit `{sha[:7]}`）\n\n{body.strip()}")
    next_step = "派 qa 依仲裁修正驗收測試 → pr.py lock" if result == "test_wrong" else "測試沒錯，派回 worker 照測試實作"
    print(f"{task_id} ruling={result} @ {sha[:7]}{note}；下一步：{next_step}")


def record(task_id: str, kind: str) -> None:
    meta = load_meta(task_id)
    if kind == "review" and needs_client_approval(meta):
        raise FlowError(f"{task_id} 是設計類任務，要甲方核可：pr.py approve {task_id}")
    sha = head_sha(meta)
    result, body = read_verdict(task_id, kind, sha)
    meta[kind] = {"result": result, "sha": sha, "by": "architect" if kind == "review" else "qa"}
    if kind == "qa" and result == "fail":
        meta["qa_fails"] = meta.get("qa_fails", 0) + 1
    save_meta(meta)
    comment(meta, f"**{LABELS[kind]}：{result.upper()}**（commit `{sha[:7]}`）\n\n{body.strip()}")
    fails = f"（第 {meta['qa_fails']} 次）" if kind == "qa" and result == "fail" else ""
    print(f"{task_id} {kind}={result} @ {sha[:7]}{fails}")
    if meta.get("qa_fails", 0) >= MAX_QA_FAILS:
        print(f"{task_id} qa 已 FAIL {meta['qa_fails']} 次：不可再重派，問甲方", file=sys.stderr)


def approve(task_ids: list[str], body: str) -> None:
    """甲方核可設計類任務（可一次多張，只跳一次確認）。settings.json 把這個指令放在 ask，甲方按允許就是核可。"""
    if not body.strip():
        raise FlowError("內容是空的：寫明甲方核可了什麼（例：D-001～D-004 照建議）")
    metas = [load_meta(task_id) for task_id in task_ids]
    for meta in metas:
        sha = head_sha(meta)
        meta["review"] = {"result": "approve", "sha": sha, "by": "甲方"}
        save_meta(meta)
        comment(meta, f"**甲方核可**（commit `{sha[:7]}`）\n\n{body.strip()}")
        print(f"{meta['task_id']} 甲方核可 @ {sha[:7]}")


def unblock(task_id: str, body: str) -> None:
    """qa FAIL 或仲裁次數達上限後，甲方決定繼續。同樣放在 ask。"""
    if not body.strip():
        raise FlowError("內容是空的：寫明甲方的決定（例：見 D-007，改用方案 B 再試）")
    meta = load_meta(task_id)
    meta["qa_fails"] = 0
    meta["rulings"] = 0
    meta["ruling"] = None  # 舊仲裁對應的是舊的 FAIL 次數，不可沿用
    save_meta(meta)
    comment(meta, f"**甲方決定繼續**（qa 失敗與仲裁次數歸零）\n\n{body.strip()}")
    print(f"{task_id} 已解除封鎖")


def comment(meta: dict, body: str) -> None:
    if meta.get("pr"):
        run("gh", "pr", "comment", str(meta["pr"]), "--body", body)


def check_ci(pr: int) -> None:
    code, output = run_status("gh", "pr", "checks", str(pr))
    if "no checks reported" in output:
        raise FlowError(f"PR #{pr} 還沒有 CI 結果：剛 push 的話 CI 可能還沒開始，用 `gh pr checks {pr} --watch` 等它跑完再合併；一直沒有就檢查 .github/workflows")
    if code == 8:
        raise FlowError(f"PR #{pr} 的 CI 還在跑，稍後再合併")
    if code != 0:
        raise FlowError(f"PR #{pr} 的 CI 沒過：\n{output}")


def task_patch_id(meta: dict) -> str:
    """任務本身變更的 patch-id（不含行號）；develop 併進來後，這張單自己的改動沒變，patch-id 就一樣。"""
    diff = run("git", "diff", f"{BASE_BRANCH}...{meta['branch']}")
    return run("git", "patch-id", "--stable", input=diff + "\n").split(" ")[0] if diff else ""


def sync(task_id: str) -> None:
    meta = load_meta(task_id)
    worktree = ROOT / meta["worktree"]
    if run("git", "status", "--porcelain", cwd=worktree):
        raise FlowError(f"{meta['worktree']} 還有沒 commit 的修改（或還沒解完的衝突），請 worker 先處理")
    if has_remote():
        run("git", "pull", "--ff-only", "origin", BASE_BRANCH)
    if run_status("git", "merge-base", "--is-ancestor", BASE_BRANCH, meta["branch"])[0] == 0:
        print(f"{task_id} 已包含最新的 {BASE_BRANCH}，不用 sync")
        return
    old_sha = head_sha(meta)
    old_patch = task_patch_id(meta)
    acceptance = card_paths(task_id, "驗收測試")
    lock_valid = bool(acceptance and meta.get("acceptance_lock")) and acceptance_unchanged(meta, acceptance)
    code, _ = run_status("git", "merge", "--no-edit", BASE_BRANCH, cwd=worktree)
    if code != 0:
        conflicts = run("git", "diff", "--name-only", "--diff-filter=U", cwd=worktree).splitlines()
        if not conflicts:
            run("git", "merge", "--abort", cwd=worktree, check=False)
            raise FlowError(f"合併 {BASE_BRANCH} 失敗（不是衝突），已還原：請看 {meta['worktree']} 的 git 狀態")
        relock = ""
        if any(path_allowed(f, acceptance) for f in conflicts):
            relock = "；衝突包含驗收測試：解完後先派 qa 確認測試沒被改壞，再 pr.py lock"
        raise FlowError(
            f"{task_id} 併入 {BASE_BRANCH} 有衝突：" + "、".join(conflicts)
            + f"；派原 worker 到 {meta['worktree']} 解衝突後 git add、git commit（不可 abort），再 pr.py open → qa → review"
            + relock
        )
    sha = head_sha(meta)
    if lock_valid:
        # 乾淨合併是 git 做的：驗收測試鎖跟著移過來（同一個測試檔兩邊都改時，patch 的上下文會變）
        meta["acceptance_lock"] = {"patch": acceptance_patch(meta, acceptance), "sha": sha, "carried_from": old_sha}
    carried = []
    if task_patch_id(meta) == old_patch:
        for kind in ("qa", "review"):
            state = meta.get(kind)
            if state and state["sha"] == old_sha:
                state["sha"] = sha
                state["carried_from"] = old_sha
                carried.append(kind)
    save_meta(meta)
    if meta.get("pr") and has_remote():
        run("git", "push", "origin", meta["branch"], cwd=worktree)
    if carried:
        note = f"任務 diff 沒變，沿用 {'、'.join(carried)}；等 CI 綠再 merge"
    else:
        note = "任務 diff 變了（或原本就沒有有效的驗證），要重新 qa、review"
    comment(meta, f"**併入最新 {BASE_BRANCH}**（`{old_sha[:7]}` → `{sha[:7]}`）：{note}")
    print(f"{task_id} 已併入最新 {BASE_BRANCH} @ {sha[:7]}：{note}")


def merge(task_id: str) -> None:
    meta = load_meta(task_id)
    if not meta.get("pr"):
        raise FlowError("還沒開 PR")
    check_main_clean()
    if has_remote():
        run("git", "pull", "--ff-only", "origin", BASE_BRANCH)
    if run_status("git", "merge-base", "--is-ancestor", BASE_BRANCH, meta["branch"])[0] != 0:
        raise FlowError(f"{BASE_BRANCH} 有這張單還沒包含的新合併：先 pr.py sync {task_id}（驗過的必須是合併後的樣子）")
    sha = head_sha(meta)
    remote_sha = json.loads(run("gh", "pr", "view", str(meta["pr"]), "--json", "headRefOid"))["headRefOid"]
    if remote_sha != sha:
        raise FlowError("本機分支與 PR 上的 commit 不一致：有沒推上去的 commit 就先 pr.py open；剛 push 的話 GitHub 要幾秒才更新，稍後再試")
    check_lane(meta)
    gates = (("qa", "pass"),) if meta.get("lane") == "fast" else (("qa", "pass"), ("review", "approve"))
    for kind, ok in gates:
        state = meta.get(kind)
        if not state or state["result"] != ok:
            raise FlowError(f"{kind} 還不是 {ok}")
        if state["sha"] != sha:
            raise FlowError(f"{kind} 驗的是舊 commit {state['sha'][:7]}，目前是 {sha[:7]}，要重新 {kind}")
    if needs_client_approval(meta) and meta["review"].get("by") != "甲方":
        raise FlowError(f"設計類任務要甲方核可：pr.py approve {task_id}")
    check_scope(meta)
    check_ci(meta["pr"])
    changed = run("git", "diff", "--name-only", f"{BASE_BRANCH}...{meta['branch']}").splitlines()
    deps_changed = [f for f in changed if is_dep_file(f)]

    # merge commit：分支上的 commit 留在歷史裡，Git Graph 看得到每張單的分支；遠端分支不刪，方便追蹤
    run("gh", "pr", "merge", str(meta["pr"]), "--merge")
    # GitHub 上已經合併：先記下來，後面的本機清理失敗也不會讓這張單卡在「沒合併」
    meta["merged"] = True
    save_meta(meta)
    run("git", "pull", "--ff-only", "origin", BASE_BRANCH)
    leftovers = []
    for cmd in (("git", "worktree", "remove", meta["worktree"]), ("git", "branch", "-D", meta["branch"])):
        code, output = run_status(*cmd)
        if code != 0:
            leftovers.append(f"{' '.join(cmd)}：{output.strip()}")
    print(f"PR #{meta['pr']} 已合併到 {BASE_BRANCH}（遠端分支保留）")
    if leftovers:
        print(
            "本機清理沒完成（不影響合併；Linux 上多半是容器留下 root 擁有的檔案，見 backend-standards 的 compose 說明），"
            "請甲方手動處理：\n  " + "\n  ".join(leftovers),
            file=sys.stderr,
        )
    else:
        print("worktree 與本機分支已清除")
    if deps_changed:
        print(f"相依檔變了（{'、'.join(deps_changed)}）：開下一張單前先 check_env.py setup 重裝環境", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="PR 工具")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("lock").add_argument("task_id")
    sub.add_parser("open").add_argument("task_id")
    rec = sub.add_parser("record")
    rec.add_argument("task_id")
    rec.add_argument("kind", choices=tuple(VERDICTS))
    sub.add_parser("ruling").add_argument("task_id")
    sub.add_parser("approve").add_argument("task_ids", nargs="+")
    sub.add_parser("unblock").add_argument("task_id")
    sub.add_parser("sync").add_argument("task_id")
    sub.add_parser("merge").add_argument("task_id")
    args = parser.parse_args()
    try:
        check_integrity()
        if args.action == "lock":
            lock(args.task_id)
        elif args.action == "open":
            open_pr(args.task_id)
        elif args.action == "record":
            record(args.task_id, args.kind)
        elif args.action == "ruling":
            ruling(args.task_id)
        elif args.action == "approve":
            approve(args.task_ids, sys.stdin.read())
        elif args.action == "unblock":
            unblock(args.task_id, sys.stdin.read())
        elif args.action == "sync":
            sync(args.task_id)
        else:
            merge(args.task_id)
    except FlowError as e:
        fail(str(e))


if __name__ == "__main__":
    main()
