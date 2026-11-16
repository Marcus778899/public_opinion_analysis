# 派工單 bbs-spike-tool

- **類型**：feat
- **負責**：backend
- **目標**：寫一次性的 BBS 延遲實驗程式 `tools/bbs_spike.py`（子命令 `probe`、`run`、`summarize`），由甲方手動執行；含節流、上限、立即停止與帳密保護
- **背景**：
  - 開工先核對 `docs/research/bbs-spike.md` 的 PyPtt 事實與 2.3.16 發布檔是否一致；對不上就回報，不自行改上限
  - PyPtt 釘 `==2.3.16`、只放 `bbs-spike` dependency group（D-043）；連線以 1 條計算（D-044）
  - 只 import `radar.collector.http`、`radar.collector.parsers.ptt`、`ptt_time`，不動 `src/radar/`
  - agent 與測試都不可連真實 PTT、不可讀 `.env`；帳密只從 `PTT_BBS_USERNAME`、`PTT_BBS_PASSWORD` 讀
- **設計依據**：`docs/development-spec.md` 7.31（B 實驗步驟與上限、C 量測方法與門檻、E 資料對應、F 的 `summary.json`、威脅與對策、派工順序第 3 列）；`docs/research/bbs-spike.md`；D-043、D-044、D-045
- **相依**：無
- **負責檔案**：
  - `tools/bbs_spike.py`
  - `pyproject.toml`
  - `uv.lock`
  - `tests/unit/tools/test_bbs_spike.py`
  - `tests/fixtures/bbs/`
- **禁區**：不改 `src/`、`infra/`、CI；不連真實 PTT；不讀 `.env`；`pyproject.toml` 只動 `[dependency-groups] bbs-spike`；fixture 手寫，不放真實推文或使用者 ID
- **驗收測試**：
  - `tests/unit/acceptance/bbs-spike-tool/`
- **驗收條件**：
  - [ ] 7.31 B 的上限全部是程式常數並有測試（登入 3 次與 10 分鐘間隔、不重試、讀取 ≥ 20 秒、`send` ≥ 1 秒且登入後才包裝、立即停止、P0 沒過拒絕 P1／P2）
  - [ ] 7.31 C 的 `U/L/E`、基準不計、網頁版配對與「未出現」、樣本下限、門檻判定都有測試
  - [ ] 帳密不出現在 log、例外、輸出檔；`summary.json` 不含使用者 ID 與推文內容
  - [ ] 沒裝 `bbs-spike` group 時 `uv run pytest tests/unit` 仍能跑
  - [ ] 開發規格 7.31 寫好甲方執行指令；行為與 7.31 有出入要回報，不自行改文件
- **驗證指令**：`make check`；`uv run pytest tests/unit/acceptance/bbs-spike-tool tests/unit/tools/test_bbs_spike.py -q`
- **回報檔**：`.agent/reports/bbs-spike-tool.json`

## 執行資訊（ae task 產生）

- Issue：#319
- 分支：`feat/bbs-spike-tool`（從 develop 開出）
- 工作目錄：`.worktrees/bbs-spike-tool`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`

## 追加 2026-11-09

- **負責檔案**：
  - `.env.example`
- **驗收條件**：
  - [ ] `.env.example` 的 `PTT_BBS_USERNAME`、`PTT_BBS_PASSWORD` 取消註解（值留空、保留說明註解），讓 `ae check-env` 當必填檢查（D-046）

## 追加 2026-11-09

### .agent/reports/bbs-spike-tool.qa.md

FAIL a5e253a

# QA bbs-spike-tool（PR #324）

## 實際執行（原始輸出摘要）
- `uv run pytest tests/unit/acceptance/bbs-spike-tool tests/unit/tools/test_bbs_spike.py -q` -> `87 passed in 0.52s`
- `uv run pytest tests/unit -n 4 -q`（含 PyPtt 已移除：`import PyPtt` -> ModuleNotFoundError）-> `2110 passed in 59.24s`，沒裝 bbs-spike group 仍能跑
- `uv run ruff check .` -> All checks passed；`ruff format --check .` -> 341 files already formatted
- `uv run pre-commit run --all-files`（含 bandit）-> 全部 Passed
- `git grep "TODO(bbs-spike-tool)"` -> 無結果
- 7.31 B 常數核對：MAX_LOGINS=3、MIN_LOGIN_INTERVAL=600、MIN_READ_INTERVAL=20(+0~5 抖動)、MIN_SEND_INTERVAL=1、WEB_POLL=60、連續失敗 3、P0 每篇 120 秒／120 次；`kick_other_session=False` 明傳、`log_level=SILENT`、send 在 login 成功後才包裝；皆符合
- `.env.example` 的 PTT_BBS_USERNAME／PTT_BBS_PASSWORD 已取消註解、值留空（D-046 條件通過）
- 手動密鑰洩漏探測（$TMPDIR 腳本，假 PyPtt 的 login 丟出訊息含帳密哨兵值的例外，走完整 `main()`）：輸出只有 `STOP: login failed: Boom`；ledger 與 p0.json 不含哨兵值
- 程式沒有寫死帳密、網址；帳密只從環境變數讀

## FAIL 項目（共 2 個）

1. 驗收條件「開發規格 7.31 寫好甲方執行指令」未達成。
   重現：`grep -n "bbs_spike.py" docs/development-spec.md` 只有 7.31 B 第 1826 行的骨架 `... python tools/bbs_spike.py …`，沒有 probe／run／summarize 各自的完整指令與參數（`--url`、`--hot-concurrent-p90`、`--rules`、`--connections-proven`、`--tail-minutes`、`--out`）。指令目前只在 `tools/bbs_spike.py` 模組 docstring。
   回報 open_questions 已提到：`docs/development-spec.md` 不在負責檔案，只有 architect 能補。需要 manager 派 architect（或擴充負責檔案）補進 7.31。

2. ledger 的「結果」欄位實際永遠是 `attempt`。
   重現：用假 PyPtt 讓 login 丟例外跑 `probe`（腳本如上），`ledger.jsonl` 內容為 `{"at": "...", "result": "attempt"}`，登入成功或失敗後都不更新。7.31 B 寫「記每次嘗試的時間與結果」。次數與間隔的限制仍正確（只看時間），所以是輕微缺口；建議登入結束後追加一筆結果（例如 ok／failed:<類別名稱>），並補成測試。

## 未能驗證（agent 不能連真實 PTT）
- get_post 的推文時間字串格式、get_screen_queue 回傳型別，要等甲方跑 P0 才能確認（回報已揭露，程式有 time_unparsed 計數）

- **負責檔案**：
  - `docs/development-spec.md`（只動 7.31 B：補甲方執行指令，`probe`／`run`／`summarize` 各一行與參數說明；其他段不動）

## 追加 2026-11-09

### .agent/reports/bbs-spike-tool.review.md

REQUEST_CHANGES bc77571

# Review bbs-spike-tool（PR #324，head bc77571）

## 檢查範圍

- `gh pr diff 324`（8 檔）對照派工單、開發規格 7.31 B／C／F／威脅表、D-043～D-046
- 負責檔案：只改負責檔案與追加的 `.env.example`、`docs/development-spec.md`（只動 7.31 B 指令段）；`src/`、`infra/`、CI 沒動。符合
- `pyproject.toml` 只加 `[dependency-groups] bbs-spike = ["pyptt==2.3.16"]`（D-043）。符合
- 7.31 B 常數、`kick_other_session=False`、`log_level=SILENT`、send 在登入後才包裝、ledger（含 qa 第 2 項修正 `update_last`）、P0 閘門：符合
- 7.31 C 的 U/L/E、基準不計、同鍵第幾個、配對與未出現、樣本下限、`N_max`、門檻判定：符合（第 3 項例外）
- 驗證：`uv run pytest tests/unit/acceptance/bbs-spike-tool tests/unit/tools/test_bbs_spike.py -q` → `95 passed`；ruff 通過；`gh pr checks 324` Check／Integration Test／Security 全 pass
- 讀 PyPtt 2.3.16 發布檔（uv 快取 `pyptt-2.3.16`）核對登入與送出流程，見下方「open_questions 逐條」

## 必須修改

1. `tools/bbs_spike.py:237-252`、`:733-745`、`:577` — 登入時的「登入太頻繁」畫面偵測不到，7.31 B「立即停止」與 P0 問題 1 沒做到。PyPtt 2.3.16 `_api_loginout.py` 的 login 對「登入太頻繁」只回 `' '` 繼續，登入照樣成功；而 `connect_core.get_screen_queue()` 是 `self._RDQ.get(1)`，**只回最後 1 個畫面**（`connect_core.py:611`），所以登入後第一次讀文章時看到的只有 get_post 的最後畫面。現在的 `check_screens` 只在 `BbsReader.read` 裡檢查這 1 個畫面，登入階段的關鍵字永遠查不到。— 改法：登入成功後（`open_session` 或 `_login` 裡、send 包裝前後皆可），用 `api.connect_core._RDQ.get(10)`（ReceiveDataQueue 保留最近 10 個畫面，比對到的畫面會在 `_decode_screen` 被 add）跑 `check_screens`，命中就登出、ledger 記 `failed: screen_keyword:…`、走 StopExperiment；只比對不存檔。這是內部介面，與包 `connect_core.send` 同樣靠 `==2.3.16` 承擔；用 `getattr` 取不到時略過，驗收測試的假 api 才不會壞。讀取時也改用同一個 `_RDQ.get(10)`（可選，但 `get(1)` 會漏掉同一次 send 中間的畫面）。補單元測試：假 connect_core 的畫面佇列含「登入太頻繁」時 `probe` 停止且登出。

2. `tools/bbs_spike.py:777-778`（probe）、`:842-843`（run）— URL 在登入**之後**才驗證與轉 AID。URL 打錯（`parse_post_url` 丟 SystemExit，或 `lib_util.get_aid_from_url` 丟 `ParameterError`）會白白用掉 3 次登入中的 1 次、還要再等 10 分鐘，且 probe 不寫 `p0.json`。已實測：假 PyPtt 讓 `get_aid_from_url` 丟例外跑 `probe`，`ledger.jsonl` 留下 `{"result": "ok"}`、輸出目錄只有 ledger。— 改法：`_load_pyptt()` 後、`_login` 前先把全部 `--url` 轉成 `PostRef`（`lib_util.get_aid_from_url` 是純字串處理，不連線），任何一個失敗就在登入前結束；補測試「URL 不合法時 ledger 沒有新增嘗試」。

3. `tools/bbs_spike.py:913-920`、`:466` — `summary.json` 的 `web` 列用了網頁版的**全部**新推文，不是「同一批推文」。7.31 C「網頁版基準：同一批推文（同一個鍵）在網頁版第一次出現的 `t_web`，用同樣公式算 U/L/E」。網頁版基準在 run 開始時建立，而 BBS 的第 2、3 篇基準在 P2 開始（10 分鐘後）才建立，P1 期間第 2、3 篇的推文只會出現在網頁版事件裡，`web` 列的樣本與 BBS 不是同一批，F「延遲表」的網頁版列會失真。— 改法：`cmd_summarize` 傳給 `build_summary` 的 `web` 只留鍵在 BBS（p1＋p2）事件裡的；補測試「只在網頁版出現的鍵不計入 web 列」。

## 不擋合併（建議）

- `tools/bbs_spike.py:576,581` — 因為 `get_screen_queue()` 只回 1 個畫面，`ReadResult.screens`／`capacity.avg_screens` 永遠 ≤ 1，7.31 C「容量：記每次讀取秒數與畫面數」的畫面數沒有意義。按第 1 項改用 `_RDQ.get(10)` 也只到 10；建議改記 send 次數即可（已有），或在報告註明。
- `tools/bbs_spike.py:861-879` — `run` 在網頁版尾段 `time.sleep` 時按 Ctrl-C，`KeyboardInterrupt` 不在 try 內，會跳過 `poller.stop_flag` 與 `finish_output_check` 的秘密掃描。建議把尾段也包進可中斷的處理。

## open_questions 逐條

1. **log.catch 印區域變數**：不成立。`radar.common.log` 用的是 `loggerhelper 2.0.0`，其 `catch`（`loggerhelper/_internal/decorators.py`）以標準 `logging` 的 `exc_info` 輸出，traceback 只有原始碼行、不含變數值（不是 loguru 的 diagnose）。實測：假 PyPtt 讓登入後的步驟丟非預期例外走完整 `main()`，`PTT_BBS_USERNAME`／`PASSWORD` 設哨兵值，stdout、stderr、`LOG_DIR`、輸出目錄 grep 哨兵值皆無結果。密碼本來就只以 `SecretStr` 持有。7.31 威脅表「`log.catch` 的 loguru 會印變數值」的敘述與實際套件不符，屬文件問題，交 manager 決定要不要請 architect 順手更正，不擋本單。
2. **TwoFactorAuthRequired 等例外**：符合 7.31 B「無法辨識的錯誤 → 立即停止、不重試」。PyPtt 2.3.16 登入可能丟 `TwoFactorAuthRequired`、`OnlySecureConnection`、`ResetYourContactEmail`、`LoginError`、`UnknownError`，程式一律包成 `BbsLoginError("login failed: <類別名>") from None`，ledger 記 `failed: …`。另：登入時「系統過載」在 PyPtt 是 break 後判斷不是主選單而丟 `LoginError`，也會停止（原因寫 LoginError 而非關鍵字）。建議 manager 在甲方前置步驟提醒「小號不要開兩階段驗證、先在瀏覽器設好聯絡信箱」。
3. **uv.lock 與登入／送出流程**：核對結果
   - lock 新增 `pyptt 2.3.16`、`autostrenum 0.0.10`、`progressbar2 4.7.0`、`python-utils 4.2.0`、`websockets 17.4`，來源皆 PyPI 並附雜湊；`requests`、`certifi`、`pyyaml` 已在既有 lock 內。全部只在 `bbs-spike` group
   - 帳密：`login` 把帳號 `[:12].strip()`、密碼 `.strip()`，存在 `api._ptt_pw`（只有 `change_pw` 會再用），組成一次 `connect_core.send(..., secret=True)` 送出，`secret` 讓 debug log 改成「隱藏敏感資訊」；SILENT 下 `log.logger.info(i18n.login_id, ptt_id)` 不輸出
   - 對外連線：只有 `wss://ws.ptt.cc/bbs`（`connect_core._websocket_endpoint`）；唯一另一個網址是 `lib_util.sync_version` 對 `raw.githubusercontent.com` 的版本檢查，只在 `API(check_update=True)` 時執行，預設 False、程式沒傳。沒有看到把帳密送往其他地方的程式
   - 送出節流：login 的 send 在包裝前呼叫（`api.connect_core.send` 於登入後才替換），登入後所有畫面操作與 logout 都經包裝層。符合 7.31 B
   - `UseTooManyResources`：websocket 模式在 `_async_send` 結尾會丟出（`connect_core.py:446`），會走立即停止。符合

## 契約問題

- 無（第 1 項是實作沒做到 7.31 B，規格本身清楚）。

- **負責檔案**：
  - `docs/development-spec.md`（本輪可再動 7.31 的「威脅與對策」小號帳密那列：loggerhelper 不印區域變數，改寫成與實際套件一致；7.31 B 前置加一句「小號不要開兩階段驗證、先在瀏覽器設好聯絡信箱」；7.31 B「立即停止」裡 get_screen_queue 的寫法依 review 第 1 項改；其他段不動）
