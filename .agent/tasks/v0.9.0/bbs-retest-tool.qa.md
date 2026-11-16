PASS 9aa9adf

# bbs-retest-tool 驗證（PR #335，worktree HEAD 9aa9adf）

## 實際執行
- `uv run pytest tests/unit/acceptance/bbs-retest-tool tests/unit/acceptance/bbs-spike-tool tests/unit/tools/test_bbs_spike.py -q` → `214 passed in 40.24s`
- `uv run pytest tests/unit -q -n auto` → `2237 passed in 58.63s`
- `uv run ruff check .` → All checks passed；`ruff format --check .` → 342 files already formatted；`pre-commit run --all-files` 全過
- `grep TODO(bbs-retest-tool)` 無結果；`git diff develop...HEAD --stat -- pyproject.toml uv.lock src infra .github` 無變動
- `retest --help`、`summarize-retest --help`：每個選項有單位、預設值、來源；`--out` 子命令前後皆可

## 仲裁
- ruling 判 TEST_WRONG（`_write_p0` 的 mkdir 缺 parents=True）；a66bea2 已照改，該測試現已通過

## 對照 7.31 G（讀程式）
- G-2 登入前檢查（時段 20:00～21:45、URL 去重、boards_ok、發文 ≤ 60 分鐘、推−噓 ≥ 30、--out 不等於 --p0 目錄）都在 `retest_precheck`，先於 ledger 與登入；拒絕 exit 3
- G-3：ledger 在 data/spike/bbs-retest、記 conn；B／C 間隔 605 秒、讀取每 60 秒；R2 至少 40、最長 60 分鐘；D-051 樣本不足不開 B、C 並寫 r2_samples_insufficient
- G-3a：多重登入關鍵字只查已開著的連線；登入後 proved 重置，A、B、C 各讀成功 1 次才證實；舊連線讀取丟白名單外例外記 kicked_or_closed；登入失敗不登出（open_session 本就不登出）；`kick_other_session=False`
- G-4：`_find_leaks` 跳過 ledger 並用英數字邊界；`_silence_pyptt_logger`；PyPtt 延遲 import（沒裝 group 也能跑單元測試）；未改 src／pyproject／uv.lock
- 無寫死帳密或網址；帳密只讀 `PTT_BBS_USERNAME`／`PASSWORD`

## open_questions 判斷（皆合理，不構成 FAIL）
1. 網頁版對照與 BBS 在同一執行緒交錯：符合 G-2「同一執行緒依序、同時只 1 個請求」，可接受
2. 尾段固定 20 分鐘、無 --tail-minutes：與 G-2 表一致；R2 立即停止才跳過尾段，符合「整個結束」
3. stop_reason 命名與 proven 規則：符合 G-3、G-5（k = 停止前最後證實數）
4. G-3a 對照 PyPtt：已自行說明；實機行為甲方跑時才能驗證（無法在此驗）
5. qualify 嚴格小於 600 秒、capacity／capacity_all 拆分：符合 G-4 #2、#3 的文字，建議 architect 於 G-8 補記

## 未能驗證／備註（非 FAIL）
- 不得連真實 PTT，未做實機；RDQ 畫面與被踢例外類別只能在甲方執行時確認
- 輕微：`cmd_retest` 只捕捉 KeyboardInterrupt／StopExperiment，其他未預期例外會讓 connections.json 與輸出掃描不執行（finally 仍會登出全部連線）。屬 minor，可排 backlog
