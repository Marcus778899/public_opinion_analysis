PASS b9d4a61

驗證環境：`.worktrees/bot-allowlist-required`，一律 `PYTHONPATH=src uv run --no-sync …`；`radar.__file__` 確認指向本 worktree 的 src。

## 驗收條件
1. 清單沒設／空且 ALLOW_ALL 非 true 啟動失敗：`check_allowlist` 在 `main()` 於連任何服務前呼叫，丟 SystemExit，訊息含 TELEGRAM_ALLOWED_CHAT_IDS 與 TELEGRAM_ALLOW_ALL。驗收測試 test_main_allowlist_unset／empty_string／only_separators／allow_all_not_true[false,False,0] 通過。
2. 清單有值只回應清單內 chat；ALLOW_ALL=true 回應全部並於啟動 warning：驗收測試 responds_only_to_listed_chat、allow_all_true_responds_to_every_chat、logs_warning 通過。實測 ALLOWED=""、ALLOW_ALL=true 執行 main()：log 出現 `WARNING ... TELEGRAM_ALLOW_ALL=true: the bot answers every chat`，之後才因缺 Postgres 設定失敗（預期，證明檢查在前）。
3. 清單有值又 ALLOW_ALL=true：清單優先並 warning，已寫入開發規格 7.21；驗收測試 list_and_allow_all_* 通過。
4. `make check` 等價（Makefile: pre-commit run --all-files + pytest tests/unit）：
   - pre-commit：trailing whitespace／end of files／check yaml／ruff／ruff format／bandit 全 Passed
   - `pytest tests/unit`：`1027 passed in 3.08s`
   - ruff check：All checks passed；ruff format --check：230 files already formatted
   - `grep -rn "TODO(bot-allowlist-required)" src tests`：無結果

## 其他檢查
- `tests/unit/acceptance/bot_allowlist/` + `tests/unit/bot/acceptance/`：26 passed；`git diff a121255 HEAD --name-only` 中 bot/acceptance 檔數 0（未被改）。
- 文件：設計 9.2 與開發規格 7.21 已同步；`.env.example` 的 `# TELEGRAM_ALLOW_ALL=false` 為註解（符合 D-009）。
- 無寫死設定值；工作樹乾淨；改動檔皆在負責檔案內。
- 注意（不擋 PASS）：README.md 第 7 行仍寫「留空代表任何找到這個 bot 的人都能訂閱」，與新行為不符。README 僅 manager 可改，請 manager 在合併前後更新。
- 回報檔誠實說明未直接跑 make check（sandbox／worktree 因素）；本次以等價指令獨立驗證。
