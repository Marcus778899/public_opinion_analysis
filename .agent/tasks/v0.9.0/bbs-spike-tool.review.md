APPROVE a0ed5e5

# Review bbs-spike-tool（PR #324，head a0ed5e5；上一輪 REQUEST_CHANGES bc77571）

## 檢查範圍

- `git diff bc77571..a0ed5e5`：只動 `tools/bbs_spike.py`、`tests/unit/tools/test_bbs_spike.py`、`docs/development-spec.md`，都在負責檔案內；驗收測試 `tests/unit/acceptance/bbs-spike-tool/` 這一輪沒改
- `docs/development-spec.md` 只動追加單允許的 3 處：7.31 B 前置（兩階段驗證、聯絡信箱提醒）、7.31 B「立即停止」（`_RDQ.get(10)` 寫法）、威脅表「小號帳密」列（改成 loggerhelper 的實際行為）。其他段沒動
- 對照 PyPtt 2.3.16 原始碼（uv 快取 `PyPtt/connect_core.py`）：`ReceiveDataQueue.get(last)` 回最後 `last` 個、只保留 10 個；`get_screen_queue()` 是 `_RDQ.get(1)`。程式的用法與它一致

## 上一輪 3 項必須修改

| # | 結果 | 依據 |
|---|---|---|
| 1 登入畫面偵測 | 已修 | `open_session` 在 `install_send_throttle` 之後用 `recent_screens(api, require_rdq=True)` 跑 `check_screens`，命中就 `_safe_logout` 並丟 `BbsLoginError("login failed: screen_keyword:…") from None`。`_login` 把 ledger 最後一筆改成 `failed: …`。`BbsLoginError` 繼承 `StopExperiment`，probe 會寫進 `p0.stop_reason`、`passed=false`。沒有 `_RDQ` 時回 `[]` 略過，驗收測試的假 api 不受影響。讀文章後也改用 `recent_screens`（有 `_RDQ` 時取 10 個）。測試：`test_probe_login_screen_with_too_often_keyword_logs_out_and_stops`、`..._clean_login_screens_continue_to_reading`、`..._without_screen_queue_skips_login_screen_check`、`test_recent_screens_prefers_rdq_ten_screens_over_single_queue` |
| 2 URL 在登入前驗證 | 已修 | `cmd_probe`、`cmd_run` 都在 `_load_pyptt()` 之後、`_login` 之前呼叫 `_parse_refs`，任何一個 URL 失敗就 `SystemExit`，這時還沒寫 ledger。例外訊息只帶類別名稱與 URL，沒有帳密。測試：`test_probe_invalid_url_exits_before_login_and_ledger`（2 組參數）、`test_probe_aid_conversion_error_exits_before_login`、`test_run_invalid_url_exits_before_login`，都檢查 `logins == 0` 而且 ledger 不存在 |
| 3 web 列只算同一批推文 | 已修 | `cmd_summarize` 先把 `web` 過濾成鍵有在 BBS（p1＋p2）出現過的，`pair_with_web` 與 `build_summary` 都用過濾後的 `web`。「未出現」仍以 BBS 的鍵計算，結果不變。鍵的「第幾個」以整篇推文清單計算（`CommentTracker.observe`），與基準時間點無關，所以 BBS 與網頁版的鍵對得起來。測試：`test_summarize_web_row_keeps_only_keys_seen_on_bbs` |

上一輪的建議「尾段 Ctrl-C」也修了：`time.sleep` 包在 `try/except KeyboardInterrupt` 裡，之後仍會執行 `poller.stop_flag` 與 `finish_output_check`。

## 驗證

- `uv run pytest tests/unit/acceptance/bbs-spike-tool tests/unit/tools/test_bbs_spike.py -q` → `104 passed in 0.47s`
- `uv run ruff check tools tests/unit/tools` → `All checks passed!`；`ruff format --check` → `11 files already formatted`
- `grep -rn "TODO(bbs-spike-tool)" src tests tools` → 無結果
- `gh pr checks 324` → Check、Integration Test、Security 全部 pass

## 不擋合併（備註）

- `_RDQ` 只留最近 10 個畫面。如果「登入太頻繁」之後 PyPtt 又走了超過 10 個畫面才回到主選單，還是會漏掉。目前 2.3.16 的登入流程看起來不會到這麼多，P0 實測時再確認
- 讀文章後改成比對 10 個畫面，文章內文剛好含「系統過載」這類關鍵字時，誤停的機會比以前高。結果偏保守（停下來），可以接受；如果真的發生，`stop_reason` 會寫出關鍵字，甲方可以自己判斷
- `capacity.avg_screens` 上限仍是 10，報告的容量以 `avg_sends` 為準（worker 回報已經提到）
