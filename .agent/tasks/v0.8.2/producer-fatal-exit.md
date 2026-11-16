# 派工單 producer-fatal-exit

- **類型**：fix
- **負責**：backend
- **目標**：JsonProducer 進入 fatal 狀態後丟 `ProducerFatalError`，各服務記 CRITICAL 並以非 0 結束，交給 docker restart 恢復（#281）
- **背景**：
  - 2026-11-04 scheduler 的 idempotent producer 出現 `_INCONSISTENT` 後所有 produce 都 `_FATAL`，外層吞掉例外，crawl.tasks 停 26 分鐘（`.agent/reports/dev-stall-recover.json`）
  - 甲方決定（D-042）：記 CRITICAL、非 0 結束，不在程式內重建 producer
- **設計依據**：`docs/development-spec.md` 7.30 A 與派工順序第 1 列；D-042
- **相依**：無
- **負責檔案**：
  - `src/radar/common/kafka/producer.py`
  - `src/radar/collector/scheduler.py`
  - `src/radar/api/main.py`
  - `tests/unit/common/kafka/test_producer.py`
  - `tests/unit/common/kafka/fakes.py`
  - `tests/unit/collector/test_scheduler.py`
  - `tests/unit/api/test_main.py`（新）
- **禁區**：不改文件（與 7.30 不符時回報 manager）；不改其他服務入口
- **驗收測試**：`tests/unit/acceptance/producer-fatal-exit/`
- **驗收條件**：
  - [ ] 三種 fatal 入口（produce 例外、delivery callback、`error_cb`）都丟 `ProducerFatalError`，且不是 `KafkaException`
  - [ ] fatal 後 `flush` 立即丟；非 fatal 錯誤行為不變
  - [ ] scheduler 列表任務與 `due_posts` 遇 fatal 都讓 main 丟出、結束碼非 0、有 CRITICAL；`BatchConsumer` 服務遇 fatal 不 commit 並結束
  - [ ] API 遇 fatal 回 503 並呼叫結束函式（先 `log.close()` 再 `os._exit(70)`）
  - [ ] `make check` 通過、改到的程式碼覆蓋率達門檻
- **驗證指令**：`make check`；`uv run pytest tests/unit/acceptance/producer-fatal-exit -v`
- **回報檔**：`.agent/reports/producer-fatal-exit.json`

## 執行資訊（ae task 產生）

- Issue：#293
- 分支：`fix/producer-fatal-exit`（從 develop 開出）
- 工作目錄：`.worktrees/producer-fatal-exit`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`

## 追加 2026-11-04

### .agent/reports/producer-fatal-exit.ruling.md

TEST_WRONG 69b2584

驗收測試 lock 檢查：跟 lock（commit b45a160）時一樣，沒被改過

觸發：worker disputes（`.agent/reports/producer-fatal-exit.json`）。依據：`docs/development-spec.md` 7.30 A「結束方式」「scheduler」兩列；派工單驗收條件第 3 條「scheduler 列表任務與 `due_posts` 遇 fatal 都讓 main 丟出、結束碼非 0、有 CRITICAL」。

## 逐條判定

| 測試 | 契約條文 | 判定與理由 |
|---|---|---|
| `tests/unit/acceptance/producer-fatal-exit/test_producer_fatal_exit_acceptance.py::test_main_list_task_fatal_stops_scheduler_and_reraises_with_critical` | 7.30 A：例外往上丟到 `main()` 的 `@log.catch(level="CRITICAL")`，記 CRITICAL | 測試錯。fixture `wired` 用 `monkeypatch.setattr(type(log), "_emit_failure", ...)` 收集 CRITICAL；但 loggerhelper 的 `Logger.catch()` 在裝飾時就把 bound method `self._emit_failure` 傳給 `_catch`（`loggerhelper/logger.py` 第 219–226 行），`scheduler.main` 在 import 時已裝飾完成，之後替換類別屬性對它無效。照契約用 `@log.catch(level="CRITICAL")` 的實作永遠收不到；能讓它過的只有在執行期另建 `log.catch` 或直接呼叫私有 `_emit_failure`，會重複送 Slack，違背契約本意。已用最小程式驗證：先裝飾、後 patch `type(log)._emit_failure`，收集結果為 `[]` |
| `tests/unit/acceptance/producer-fatal-exit/test_producer_fatal_exit_acceptance.py::test_main_due_posts_fatal_stops_scheduler_and_reraises_with_critical` | 同上 | 測試錯，原因同上（共用 `wired` fixture） |

實作本身：`src/radar/collector/scheduler.py` 的 `main()` 仍有 `@log.catch(level="CRITICAL")`，`_logged(..., on_fatal)` 包住列表任務、`due_posts`、`sync_boards`、`lock`，`on_fatal` 記 `log.critical` 並 `scheduler.shutdown(wait=False)`，`finally` 後 `raise fatal[0]`，符合 7.30 A。兩個測試的其他斷言（`pytest.raises(ProducerFatalError)`、`shutdown_calls == [{"wait": False}]`）在實跑時都已通過，失敗只在 CRITICAL 斷言。

## 測試應該怎麼改（qa）

把 `wired` fixture 收集 log 的方式改成攔截執行期才查找的 `_resolve`（`_emit` 與 `_emit_failure` 都在呼叫時走 `self._resolve().log(level, ...)`）：

- 移除 `monkeypatch.setattr(type(log), "_emit_failure", ...)`
- 改成 `monkeypatch.setattr(log, "_resolve", lambda: recorder)`，`recorder` 是有 `log(self, level, *args, **kwargs)` 方法、把 `level` 存進 `state.emitted` 的物件（`level` 是數字，`is_critical` 已接受 `50`）
- 已驗證：先裝飾 `@log.catch(level="CRITICAL")`、後 patch `log._resolve`，收到 `[50]`
- `test_main_ordinary_job_error_does_not_stop_scheduler` 共用此 fixture，改後仍成立（一般錯誤走 `log.exception`，等級 ERROR）
- `test_api_fatal_logs_critical` 同樣 patch `_emit_failure`，但另 patch 了 `api_main.log.critical`，目前會過；建議一併改成同一種攔截法，免得留下失效的 patch

## 其他

- worker open_questions 的 `tests/unit/acceptance/import-model-hardening/...::test_cli_prints_package_sha256_without_option` 全套偶發失敗不在本單範圍，不判；建議 manager 另開 issue 追蹤。
- 契約問題：無。

manager 補充：仲裁「其他」提到的 import-model-hardening 測試不在本單範圍，不要改；本輪只依仲裁修正 producer-fatal-exit 驗收測試的 `wired` fixture 收集 log 方式（及建議一併改的 `test_api_fatal_logs_critical`），worker 不需改實作，修正後重跑確認全過。
