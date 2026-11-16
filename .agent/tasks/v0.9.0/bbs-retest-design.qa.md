PASS 1d916a4

# QA bbs-retest-design（PR #331，docs 單）

- 變更檔：`git diff --name-only develop...HEAD` 只有 `docs/development-spec.md`（+123 −2），符合負責檔案；src/、tools/、infra/、tests/ 未動。
- 驗收條件 1：7.31 G 含 G-2 步驟、G-3 上限（含多連線）與立即停止、G-5 量測與門檻、混合方案判定、樣本下限（≥100 則、≥3 篇）。通過。
- 驗收條件 2：G-7 派工順序（task_id、負責、負責檔案、驗收測試目錄）、G-9 需調查、G-10 待決定。通過。
- 驗收條件 3：威脅表 O-1 說法已改（SILENT 僅登入時有效，get_board_info 會 log.init(INFO)）。已核對 .venv PyPtt `_api_get_board_info.py:16` 為 `log.init(log.DEBUG if call_by_others else log.INFO)`。通過。
- G-3a 對照本機 PyPtt 2.3.16 `_api_loginout.py`：kick_other_login_response 依 kick_other_session 回 y/n，並有 TargetUnit('您想刪除其他重複登入的連線嗎')，與文件所述一致。
- 指令輸出：
  - `uv run ruff check .` -> All checks passed!
  - `uv run ruff format --check .` -> 341 files already formatted
  - `uv run pytest tests/unit/acceptance/bbs-spike-tool -q` -> 79 passed
  - `uv run pytest tests/unit -q -n 4` -> 2127 passed
  - `pre-commit run --all-files` -> 全部 Passed（trailing whitespace、end of files、yaml、ruff、ruff format、bandit）
- 無 `TODO(bbs-retest-design)` 殘留；無寫死設定值（文件只用變數名稱）。
- 非阻擋備註：docs/research/bbs-multi-login.md 與 PyPtt 實際行為不符（回報 open_questions 已提），是否更正由 manager 決定。
