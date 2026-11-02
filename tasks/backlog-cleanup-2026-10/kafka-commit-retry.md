# 派工單 kafka-commit-retry

- **類型**：fix
- **負責**：backend
- **目標**：共用 consumer 的 commit 遇到暫時性 Kafka 錯誤時重試，不讓服務崩潰
- **背景**：2026-10-21 開發環境 Kafka 因主機記憶體不足重啟，inference 反覆崩潰：`_commit` 拋出 `KafkaError COORDINATOR_LOAD_IN_PROGRESS`（radar_inference log，`src/radar/common/kafka/consumer.py` `_commit` 只放過 `_LOST_ASSIGNMENT_CODES`）。CLAUDE.md「暫時性錯誤重試」；所有用 `radar.common.kafka.consumer` 的服務都受影響
- **設計依據**：`docs/development-spec.md` 2.2（Kafka、commit 失去 assignment 不中止）；`src/radar/common/retry.py`（既有退避）
- **相依**：無
- **負責檔案**：
  - `src/radar/common/kafka/consumer.py`
  - `tests/unit/common/kafka/test_consumer.py`
  - `docs/development-spec.md`（2.2 補 commit 暫時性錯誤的處理）
- **禁區**：不改「處理完才 commit」的語意，不可改成非同步 commit 或跳過 commit 繼續消費；失去 assignment 的既有處理不變；不改各服務入口；不新增相依套件；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：
  - `tests/unit/acceptance/kafka-commit-retry/`
- **驗收條件**：
  - [ ] commit 遇到可重試的錯誤（至少 COORDINATOR_LOAD_IN_PROGRESS、COORDINATOR_NOT_AVAILABLE、NOT_COORDINATOR，或以 librdkafka 的 retriable 判斷）會退避重試，成功後繼續消費；重試期間收到停止訊號能結束、不 commit 未處理完的批次
  - [ ] 重試超過上限仍失敗才拋出（上限與退避沿用或對齊 `radar.common.retry`）；不可重試的錯誤照舊拋出；失去 assignment 照舊只記 warning
  - [ ] 每次重試記一行 WARNING（錯誤碼、第幾次）
  - [ ] 驗收測試全過；`make check` 通過；PR 的 CI 全綠
- **驗證指令**：`make check`
- **回報檔**：`reports/kafka-commit-retry.json`

## 執行資訊（task.py 產生）

- Issue：#144
- 分支：`fix/kafka-commit-retry`（從 develop 開出）
- 工作目錄：`.worktrees/kafka-commit-retry`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

### reports/kafka-commit-retry.review.md

REQUEST_CHANGES d982194

# Review kafka-commit-retry（PR #145，head d982194）

## 檢查範圍

| 項目 | 結果 |
|---|---|
| 負責檔案 | 只改 `consumer.py`、`test_consumer.py`、`development-spec.md`；`tests/unit/acceptance/kafka-commit-retry/` 是 qa 的 `7edaf29`，worker 沒改 |
| 禁區 | 仍然是同步 commit，「處理完才 commit」沒變；失去 assignment 的分支排在重試判斷前面，行為不變；沒改服務入口，沒加相依套件 |
| 驗收條件 1～3 | 實作符合：可重試的錯誤碼有 3 個；用 `self._backoff()` 退避；stop 會在等待前、等待後各檢查一次；每次重試記一行 WARNING（code、n/6） |
| 寫死設定 | 沒有 port、網址、token；`_COMMIT_MAX_RETRIES` 的判斷見下方「問題一」 |
| 安全與 bug | 沒有阻擋性的 bug；有一個小風險見「建議 A」 |
| 驗證 | `uv run pytest tests/unit/common/kafka tests/unit/acceptance/kafka-commit-retry -q --cov=radar.common.kafka.consumer` → 115 passed，consumer.py 覆蓋率 95%，沒測到第 260–261 行；`gh pr checks 145` 的 Check、Integration Test、Security 都 pass |

## 問題一：上限 6 次寫成常數、不開環境變數，是否恰當

恰當，維持常數。

- 它不是部署相關的設定（port、domain、token 這類），是可靠性的內部參數。上限、退避、`max.poll.interval.ms` 三者一起決定安全邊界：預設的 `backoff_delays` 會等 0.5+1+2+4+8+16 = 31.5 秒，小於 librdkafka 預設的 300 秒（`consumer_config` 沒有覆寫）。開成環境變數，有人調大後就可能超過 `max.poll.interval.ms`，重演 #11。
- 目前沒有服務注入自訂的 `backoff=`（`grep -rn "backoff=" src/radar` 沒有結果），31.5 秒的估算在所有服務都成立。
- 條件：開發規格要寫出「為什麼是 6」（見 R1），以後有人改退避或 `max.poll.interval.ms` 才知道要一起檢查。

## 問題二：重試期間不 poll，和開發規格 2.2「重試期間 pause/resume」是否一致

設計可以接受，但文件目前前後矛盾，必須修（R1）。

- 2.2 的「重試期間」那一列，是 #11 針對 handler 的 `TransientError` 立的規則：重試不限時間，所以必須持續 poll。commit 重試有上限，總長 31.5 秒，遠小於 `max.poll.interval.ms`。另外心跳由 librdkafka 的背景執行緒送，不 poll 也不會被踢出 group。
- 就算真的發生 rebalance，commit 會被 broker 以 `UNKNOWN_MEMBER_ID` 或 `ILLEGAL_GENERATION` 拒絕，走既有的 warning 分支，不會 commit 到別人的 partition。重試期間不呼叫 `consume`，不會多拉資料，所以不需要 pause。
- 代價：重試期間沒人處理 rebalance callback，其他成員的 rebalance 最多會被拖住約 31.5 秒。這時 coordinator 本來就不健康，可以接受。
- 不一致的地方：2.2 寫著「重試上限：…`BatchConsumer` 不設上限」，現在 `BatchConsumer` 的 commit 有 6 次上限，兩句直接矛盾。「重試期間：pause 並持續 poll；只 sleep 不 poll 會被踢出」也沒有標明只適用 handler 重試，讀者會以為 commit 重試違反了 #11 的規則。

## 必須修改

1. `docs/development-spec.md:136-138` — 「重試期間」「重試上限」兩列沒有限定是 handler（`TransientError`）的重試，和新加的 commit 重試（有上限、不 poll）矛盾 — 改法：兩列開頭加上「handler 拋 `TransientError` 時」；「commit 失敗」那一列補一句「commit 重試不 poll：總等待約 31.5 秒，小於 `max.poll.interval.ms`（預設 300 秒）；調整退避、上限或 `max.poll.interval.ms` 時要一起檢查」。
2. `tests/unit/common/kafka/test_consumer.py:430-438`（`test_commit_retry_beyond_limit_raises`）— 只驗證「最後會拋出」，沒驗證「重試滿 6 次才拋」：實作改成重試 2 次或 40 次都會通過，驗收條件 2 沒有真的被測到 — 改法：準備 50 個錯誤，斷言拋出時剛好用掉 7 個（第 1 次 commit 加 6 次重試，`len(errors) == 43`）；再加一個邊界測試：給 6 個錯誤，第 7 次 commit 成功，就不拋出、`fake.commits == 1`。
3. `src/radar/common/kafka/consumer.py:259-261` — 「等待期間收到停止訊號」是 SIGTERM 最常落在的時間點，這個分支沒有任何測試（覆蓋率報告缺第 260–261 行）；驗收測試只測到第 247 行「等待前已經 stop」 — 改法：在 `test_consumer.py` 加一個單元測試，把 `consumer._stop` 換成 `wait()` 時會自己 set 的 Event 子類別，斷言 `fake.commits == 0`、不拋出、`fake.closed`。

## 建議（不擋合併）

- A. `consumer.py:258` 的 `self._stop.wait(delay)` 跑在主執行緒，而 `_on_signal` 也在主執行緒呼叫 `Event.set()`。如果訊號剛好在 `Event.wait` 持有內部 `Condition` 鎖的那一小段進來，`set()` 會等同一把不可重入的鎖，造成死結。結果是等到 compose 的 `stop_grace_period` 後被 SIGKILL，資料不會遺失，只是該批重做。既有的 `_wait_keeping_membership` 只用 `is_set()`，沒有這個問題。可以改成用 `time.sleep(min(remaining, 1.0))` 分段等待、每段檢查 `is_set()`（時間來源沿用 `self._clock`）。
