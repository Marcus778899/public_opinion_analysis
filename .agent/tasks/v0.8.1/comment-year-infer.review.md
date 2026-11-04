APPROVE 4993a7b

# Review comment-year-infer（PR #211，第二輪）

## 上一輪兩項

| 項目 | 結果 |
|---|---|
| 問題 1：「不早於文章時間」的退一年分支走不到 | 已處理。`ptt.py:194-209` 改成「補成隔年（台北年份 > 文章台北年份）且晚於爬取時間 + 1 天 → 退回文章年份，退後仍須 ≤ 爬取時間 + 1 天；其餘未來時間回 None 並 log.warning」。這條分支走得到：`parse_comment_time` 在推文月份 < 文章月份時補 +1 年，正是這個條件 |
| 問題 1：單元測試輸入要是 parser 會產生的 | 已處理。`test_ptt_comment_bound.py` 的 2027-05-01（文章 10 月、推文 05/01）、2026-11-05（月份 ≥ 文章月份，同年）、2028-02-29（文章 2027/10、推文 02/29 補成閏年 2028）都是 `parse_comment_time` 會產生的值；`test_step_back_still_in_future_becomes_none` 對應文章標頭時間晚於爬取時間的情況，也是可輸入的 |
| 問題 2：回報的根因推測 | 已處理。`reports/comment-year-infer.json` 撤回舊推測，改寫抽樣結果（PG + Kafka raw.html，沒有對 PTT 發請求）：轉錄／修改把舊推文帶進新文章；qa 用 PG 獨立對過 B3C、EA9 兩筆。NULL 的成因（PTT 截斷長推文，缺 HH:MM）已寫進 2.1 |
| 2.1 和實作一致 | OK（`docs/development-spec.md:126` 逐項對過 `_bounded_comment_time`） |

## 其他檢查

| 項目 | 結果 |
|---|---|
| 改到的檔案 | 都在負責檔案內；`git diff b78037e HEAD` 只動 ptt.py、test_ptt_comment_bound.py、2.1；驗收目錄沒動 |
| 驗收測試 | `uv run pytest tests/unit/acceptance/comment-year-infer tests/unit/collector -q` → 168 passed（我重跑過） |
| 寫死設定值、安全 | 沒有；log 只記時間值，沒有個資 |
| 不早於文章時間的限制拿掉後 | 符合 manager 補充（抽樣已證實「推文時間早於文章標頭時間」，保留真實時間） |

## worker 提出的限制：推文月份 ≥ 文章月份但落在未來（例 文章 10/28、推文 11/05）→ NULL

**判定：本單可以接受，不需要另外開單；有需要可以列進 backlog。**

| 理由 | 說明 |
|---|---|
| 符合契約 | 驗收條件 2 寫「回 NULL 或依規則處理，並記 log」；2.1 也寫了「其餘…回 NULL 並記 log」，實作、規格、鎖定的驗收測試三者一致，不是 dispute |
| 影響小 | 我查開發 PG（`docker compose … exec postgres psql`）：目前晚於 now + 1 天的推文 251 則，+1 年型（這次會還原）219 則／47 篇，同年型（會變 NULL）32 則／8 篇，約 13% |
| 還原只是猜測 | 同年型推文的真實年份只能確定不是文章年份，退一年（例 2025-11-05）是猜的，也可能是更早；寫成 NULL 不會產生錯誤的資料。+1 年型退回文章年份同樣是猜「最近一年」，但至少是 parser 原本規則唯一的另一個候選值 |
| 改要動鎖定的測試 | `test_unreasonable_comment_time_logs_one_warning` 要求回 None；要改得 qa 重寫並改 2.1，成本跟收益不成比例 |

如果之後要讓兩型一致（同年型也退一年），要開新單一起改 2.1 跟驗收測試（qa 重新鎖）。

## 非阻擋（交給 manager）

- 已入庫的錯誤資料（未來時間 251 則、NULL 68 則）要重爬或回填，本單不處理；回填時 +1 年型可以直接套新規則
- 帶入的舊推文如果沒有落在未來（例 10/20 文章裡的 10/05 推文），會照原樣存成錯誤年份，偵測不到；屬於同一類資料，如果要處理再另外評估
