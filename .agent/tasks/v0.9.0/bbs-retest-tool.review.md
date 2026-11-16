APPROVE 9aa9adf

# bbs-retest-tool review（PR #335，head 9aa9adf）

## 檢查範圍
- `gh pr diff 335`：`tools/bbs_spike.py`（+672／-54）、`tests/unit/tools/test_bbs_spike.py`、qa 的 `tests/unit/acceptance/bbs-retest-tool/`；沒有動到負責檔案以外（src、infra、CI、pyproject、uv.lock 無變動）
- 對照：派工單、開發規格 7.31 B／C／G（G-1～G-5、G-8）、D-049、D-051；worker 回報 open_questions；qa 結果
- CI：Check、Integration Test、Security 全部 pass（`gh pr checks 335`）

## 逐項對照（皆符合）
| 規格 | 實作 | 判定 |
|---|---|---|
| G-2 登入前檢查 | `retest_precheck`：`--out`≠`--p0` 目錄、p0 通過、20:00≤開始<21:45（`check_start_window`）、URL 不重複、`boards_ok`、檔名時間 ≤60 分、網頁版推−噓 ≥30（`web_score`）、ledger 上限；全部在 `Ledger.record` 與登入之前，拒絕 exit 3 | 符合 |
| G-3 ledger | `_RETEST_OUT`＝`data/spike/bbs-retest`；`Ledger.record(..., conn)`；`_login_with` 每條連線都過 `check_login_allowed`（3 次、10 分鐘跨連線）；連線數 min(`--connections`, 剩餘次數) | 符合 |
| R2 40／60 分、D-051 | `run_r2`：最短 `R2_MIN_SECONDS`、樣本達 100 則且 3 篇提前結束、最長 60 分；不足回傳 False，`cmd_retest` 不進 `run_m`，`stop_reason=r2_samples_insufficient` | 符合 |
| M 開線與讀取 | `run_m`：前一條登入 +605 秒開下一條；B／C 60 秒、A 20＋0～5 秒；`proved` 在開線時重置，全部各讀成功 1 次才 `proven=len(conns)`；停止時 k 保留上一次證實數 | 符合 |
| G-3a | `kick_other_session=False` 照舊；`_MULTI_LOGIN_KEYWORDS` 只在 `_is_old` 的連線讀取後查；舊連線白名單外例外記 `kicked_or_closed:<conn>`；B／C 登入失敗為 `BbsLoginError`（StopExperiment 子類），沒加進 `conns`，不登出不送鍵。我另外對照 `.venv` PyPtt 2.3.16：`_api_loginout.py:61-62`、`:98` 與 worker 說法一致；`ReceiveDataQueue` 只留最後 10 個畫面，舊連線的佇列不會殘留自己登入時的多重登入字樣 | 符合 |
| G-4 #1 O-2 | `_find_leaks` 跳過 `ledger.jsonl`、`_secret_pattern` 英數字邊界 | 符合 |
| G-4 #2 F-1 | `qualify_posts`／`is_hot`，`cmd_summarize` 也套用、列 `excluded` | 符合 |
| G-4 #3 #327 | `_capacity` 只用判定階段，`capacity_all` 全程 | 符合 |
| G-4 #4 O-1 | `_silence_pyptt_logger` 在每次 `ptt.API()` 之後 | 符合 |
| G-4 #5 #328 | 各選項 help 有單位／預設／來源；`--out` 子命令前後皆可（SUPPRESS） | 符合 |
| G-5 | `decide_retest` 三項；summary 有 `capacity.n_max`、`connections_needed`、`mixed.coverage_of_p90`、`connections`；沒有 user_id、推文內容、帳密 | 符合 |
| 既有簽名 | `decide`、`scan_and_purge`、`finish_output_check`、`build_summary` 未改；`Ledger.record` 只加選填參數 | 符合 |

## 不擋合併的發現（建議由 manager 決定是否處理）
1. `tools/bbs_spike.py:1384`（`open_conn` 設 `ready_at=time.monotonic()`）— 與 G-3a「開 B、C 後，下一輪**先**讓 A（與 B）各讀 1 次」順序不同：R2 剛讀完 A 就結束時，A 的下一次讀取在 20～25 秒後，B 登入只要幾秒，所以 B 會先讀；開 C 時 B 最多晚 60 秒才讀。偵測條件（舊連線讀取失敗即停）本身正確、qa 測試也有鎖住；先讀後讀只影響偵測時間差（≤60 秒、新連線多讀 1 次），不增加帳號風險。處置二選一：(a) 回寫規格 G-8 改成「依原排程，舊連線在下一次輪到時讀」；(b) 小修 `open_conn`，讓新連線的 `ready_at` 不早於舊連線的 `ready_at`。我建議 (a)
2. `cmd_retest` 只捕捉 `KeyboardInterrupt`／`StopExperiment`（qa 的 minor）：其他未預期例外時 `finally` 仍登出全部連線，但不寫 `connections.json`、不跑 `finish_output_check`。寫法與既有 `cmd_run` 一致，可能出例外的路徑（讀取、網頁版、時鐘、登入）都已經轉成 StopExperiment 或吞掉；排 backlog 即可
3. `retest_precheck` 只擋 `--out` 等於 `--p0` 所在目錄；`--out` 設成上層（例如 `data/spike`）時，輸出掃描會遞迴進第一次實驗的目錄。規格只要求「等於」就拒絕，而第一次的 ledger 已經不在掃描範圍內；這次不擋，可在 backlog 改成「`--p0` 目錄在 `--out` 底下也拒絕」

## worker open_questions 判斷
| # | 項目 | 是否可接受 | 是否回寫規格 |
|---|---|---|---|
| 1 | 網頁版對照與 BBS 同一執行緒交錯、第一次 BBS 讀取完才開始 | 可，符合 G-2「同一執行緒依序、同時只 1 個請求」 | G-8 補一行 |
| 2 | 尾段固定 20 分（沒有 `--tail-minutes`）；D-051 不足與 M 停止時仍跑尾段，R2 立即停止才跳過 | 可，G-1 沒有列這個選項；不足時跑尾段可以多留 Q5 資料 | G-8 補一行 |
| 3 | `stop_reason` 用語（`r2_samples_insufficient`、`kicked_or_closed:A`、`multi_login_warning:A`、`<例外>:B`、`not_proven_in_time`） | 可。`not_proven_in_time`（B／C 登入後 600 秒內沒全部讀成功就停）是規格沒寫的**新增停止條件**，比較保守，不違反 D-049 | 要回寫：G-3 停止條件加這條，報告才解讀得了 |
| 4 | G-3a 對照 2.3.16 | 已確認（見上表） | 不用 |
| 5 | 開線間隔 605 秒、B／C 60 秒無隨機、統一排程 | 可，符合 G-3「≥」 | G-8 補一行 |
| 6 | `is_hot` 嚴格 < 600 秒；run_id／post_id 解析不出的列 `post_age_unknown` | 可，依標示的分鐘計，10 個相鄰分鐘跨 540 秒 | G-8 補一行 |
| 7 | `capacity`／`capacity_all` 鍵、`mixed.covered_posts`／`coverage_of_p90` | 可，符合 G-4 #3、G-5 | G-5 的 summary 欄位名稱可補 |

建議：以上回寫（含發現 1 的處置 (a)）併進 `bbs-retest-report` 補 7.31 G 結論時一起寫；這張單不用改。
