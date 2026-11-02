APPROVE 8253391

# Review kafka-commit-retry（PR #145，head 8253391，第二輪）

## 上一輪必修 3 條

| 必修 | 結果 |
|---|---|
| R1 `docs/development-spec.md` 2.2 | 已處理。「重試期間」「重試上限」兩列開頭限定為「handler 拋 `TransientError` 時」或「handler 的重試」，「重試上限」也註明 commit 重試另有上限；「commit 失敗」那一列補上「不 poll、6 次共約 31.5 秒、小於 `max.poll.interval.ms`、調整時要一起檢查」。前後不再矛盾 |
| R2 上限測試 | 已處理。`test_commit_retry_beyond_limit_raises_after_exactly_six_retries` 斷言 `len(errors) == 43`，表示剛好用掉 7 個錯誤；`test_commit_succeeds_on_last_allowed_retry` 給 6 個錯誤，第 7 次成功時斷言 `commits == 1`。上限改成 5 或 7 都會讓其中一個測試失敗 |
| R3 等待期間收到 stop | 已處理。`test_stop_during_commit_retry_wait_leaves_batch_uncommitted` 換掉 `wait()`，讓它在等待時 set。這個測試有鑑別力：只放 1 個錯誤，如果拿掉 `consumer.py:259-261`，下一次 commit 會成功、`commits == 1`，測試就會失敗。覆蓋率報告不再缺第 260–261 行 |

## 照常審查

| 項目 | 結果 |
|---|---|
| 新 commit 的範圍 | `d982194..8253391` 只改 `docs/development-spec.md`、`tests/unit/common/kafka/test_consumer.py`；`consumer.py` 沒有再改，上一輪看過的實作照舊 |
| 負責檔案 | PR 一共改了 4 個檔案。`tests/unit/acceptance/kafka-commit-retry/` 只有 qa 的 `7edaf29`（`git log 7edaf29..HEAD -- tests/unit/acceptance` 沒有結果），worker 沒有改 |
| 禁區 | 仍是同步 commit；失去 assignment 的分支排在重試判斷前面；沒改服務入口、相依套件、`scripts/`、`.claude/`、`contracts/`、`CLAUDE.md` |
| 寫死設定 | 沒有寫死的設定；`_COMMIT_MAX_RETRIES` 的判斷維持上一輪的結論（內部常數，規格已寫理由） |
| 驗證（本次實際執行） | `uv run pytest tests/unit/common/kafka tests/unit/acceptance/kafka-commit-retry -q --cov=radar.common.kafka.consumer --cov-report=term-missing` → 117 passed，consumer.py 96%，缺 134、195-197、266、277-278，都是這次沒改的行；`ruff check` 通過；`ruff format --check` 顯示 259 files already formatted；`grep -rn "TODO(kafka-commit-retry)" src tests` 沒有結果；`gh pr checks 145` 的 Check、Integration Test、Security 都是 pass |

## 建議 A 的判斷：風險確實存在、嚴重度低，開 backlog issue 即可（不是本單必修）

### 風險確實存在

- 這個環境是 Python 3.12.3。`threading.Event.wait` 的寫法是 `with self._cond: signaled = self._flag; ... self._cond.wait(timeout)`，而 `Event` 的 `_cond` 是 `Condition(Lock())`，用的是**不可重入**的鎖。
- CPython 的 signal handler 在主執行緒的位元組碼之間執行。主執行緒在 `Event.wait` 裡持有 `_cond` 鎖的時候，訊號可能剛好進來，有兩個時間窗：進入時 `with` 到 `_release_save` 之間，以及醒來後 `_acquire_restore` 到離開 `with` 之間。這時 `_on_signal` 會呼叫 `stop()`，再呼叫 `Event.set()`，也就是 `with self._cond:`，於是同一個執行緒等待自己持有的鎖，永遠等不到。
- 真正阻塞在 `waiter.acquire(timeout)` 時，`_cond` 已經釋放了。這時訊號進來，handler 照常 set，可以正常喚醒，所以只有上面兩個時間窗有問題。
- 改這張單之前，主執行緒只用 `is_set()` 讀 `_stop`，那個方法不拿鎖。這張單的 `consumer.py:258` 是第一個讓主執行緒持有 `_stop._cond` 的地方。另外，專案裡 `collector/scheduler.py:153` 刻意用新建的 `threading.Event().wait(poll_s)` 來等待，配合 `stopping.is_set` 判斷，也避開了這個模式。

### 嚴重度：低

| 面向 | 評估 |
|---|---|
| 觸發條件 | 三件事要同時成立：①commit 正在重試，只有 coordinator 不健康時才會發生，一年可能遇到幾次；②這時剛好收到 SIGTERM 或 SIGINT；③訊號剛好落在每次 wait 前後幾 µs 的時間窗裡。③占 31.5 秒等待時間的比例大約是 10⁻⁶ |
| 後果 | 程式卡住，等到 compose 的 stop grace period 後被 SIGKILL。批次沒有 commit，會由下一個成員重做；處理是冪等的，不會遺失或重複寫入資料。不會影響正在運作的服務，只會讓這一次關閉變慢 |
| 和本單目標的關係 | 本單要修的是「Kafka 重啟時服務崩潰」，這已經修好了。這個風險不會讓修好的行為退回去，也不違反驗收條件或禁區 |

所以不擋合併，開 backlog issue。

### 可直接貼成 issue 的說明

```markdown
標題：BatchConsumer commit 重試的 Event.wait 與 signal handler 可能互等（低機率關閉卡住）

## 現象（理論上可能發生，尚未觀察到）
`src/radar/common/kafka/consumer.py` 的 `_commit()` 在 commit 重試時會呼叫 `self._stop.wait(delay)`（#144 / PR #145 加入）。
`_on_signal` 在主執行緒呼叫 `self._stop.set()`。`threading.Event` 的 `_cond` 是 `Condition(Lock())`，鎖不可重入：
如果訊號剛好在 `Event.wait` 持有 `_cond` 的那一小段進來（進入 `with` 到開始阻塞之間，或醒來後到離開 `with` 之間），
`set()` 就會等主執行緒自己持有的鎖，造成死結。

## 影響
- 只在「commit 正在重試」（coordinator 不健康）時收到 SIGTERM/SIGINT 才可能發生，機率約 10⁻⁶
- 後果是關閉卡到 stop grace period 後被 SIGKILL；批次沒有 commit，下一個成員會重做（冪等），資料不會遺失

## 改法
- `_commit` 的等待改成分段 sleep，每段檢查 `is_set()`；不在主執行緒對 `_stop` 呼叫 `wait()`：
  `deadline = self._clock() + delay`；當 `not self._stop.is_set()` 且 `remaining > 0` 時 `time.sleep(min(remaining, 0.5))`
  （sleep 改成可注入，單元測試用 fake，不真的等待）
- `time.sleep` 被訊號中斷時，handler 執行期間不持有任何鎖；每段最多 0.5 秒，收到停止訊號後最晚 0.5 秒內結束
- 跟 `collector/scheduler.py` 的 `wait_until_acquired` 一樣，只用 `is_set()` 判斷停止
- 開發規格 2.2「commit 失敗」那一列不需要改，行為沒有變

## 驗收
- 單元測試：在等待中途 stop，斷言最晚一段 sleep 內就結束、`commits == 0`、不拋出、consumer 已 close
- `grep -n "_stop.wait" src/radar` 沒有結果
- `make check` 通過
```
