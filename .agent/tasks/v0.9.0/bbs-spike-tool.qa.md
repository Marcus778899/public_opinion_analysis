PASS a0ed5e5

# QA bbs-spike-tool（PR #324，head a0ed5e5）

## 實際執行
- `uv run pytest tests/unit/acceptance/bbs-spike-tool tests/unit/tools/test_bbs_spike.py -q` -> `104 passed in 0.43s`
- `uv run pytest tests/unit -n 4 -q` -> `2127 passed in 59.41s`
- 擋住 PyPtt（PYTHONPATH 放會 raise ImportError 的 PyPtt.py）跑 acceptance＋tools 測試 -> `127 passed`，沒裝 bbs-spike group 仍能跑
- `uv run ruff check .` -> All checks passed；`ruff format --check .` -> 341 files already formatted；`pre-commit run --all-files`（含 bandit）全 Passed
- `git grep "TODO(bbs-spike-tool)"` -> 無結果
- `gh pr checks 324`：Check pass、Security pass、Integration Test 驗證時仍 pending（非本單程式路徑）

## 驗收條件
- 7.31 B 常數與測試（登入 3 次／10 分鐘、不重試、讀取 >= 20 秒、send >= 1 秒且登入後才包裝、立即停止、P0 閘門）：測試通過，程式核對符合
- 7.31 C（U/L/E、基準、配對、樣本下限、門檻）：測試通過
- 帳密：手動用假 PyPtt 跑完整 `main()`（帳密設哨兵值）-> 輸出目錄與 LOG_DIR 無哨兵值；程式無寫死網址與帳密，只讀 `PTT_BBS_USERNAME`／`PTT_BBS_PASSWORD`
- `.env.example` 兩個變數已取消註解、值留空（D-046）
- 開發規格 7.31 B 已有 probe／run／summarize 完整指令與參數說明

## 上輪 FAIL 與 review 三項的手動重現（假 PyPtt，$TMPDIR）
1. 登入後 `_RDQ.get(10)` 含「登入太頻繁」-> 輸出 `LOGIN CALLED`、`LOGOUT`、`STOP: login failed: screen_keyword:登入太頻繁`；ledger 該筆更新為 `failed: login failed: screen_keyword:…`（不新增一筆）。已修
2. URL 不合法（格式錯、或 `get_aid_from_url` 丟 ValueError）-> 登入前即 `invalid url`／`not a PTT post url` 結束，輸出目錄沒有 ledger、`API` 未建立。已修
3. 正常登入 -> ledger 單筆 `result: ok`。已修
4. `cmd_summarize` 的 web 事件只留鍵在 BBS（p1＋p2）內者（程式碼核對，且有測試）。已修

## 未能驗證（agent 不能連真實 PTT）
- 真實 PTT 上 `_RDQ` 畫面實際文字是否含「登入太頻繁」、get_post 推文時間字串格式：要等甲方跑 P0。PyPtt 2.3.16 安裝檔核對 `ReceiveDataQueue.get(last)` 與 `_RDQ` 屬性存在，與程式假設一致
- 文件備註（不擋）：avg_screens 受畫面佇列上限限制，報告以 send 次數為準
