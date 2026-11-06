# 派工單 comment-year-infer

- **類型**：fix
- **負責**：backend
- **目標**：修正推文時間補年份的錯誤，讓 `commented_at` 不再落在未來（#179）
- **背景**：ClickHouse `comments_latest` 近 7 天約 300 則 `commented_at` 落在 2026-11～2027-09，推測 parser 補年份時跨年判斷錯；另 60 則為 NULL（請一併查原因，屬於 parser 解析失敗就一起修，屬於 PTT 原始資料本來沒有時間就在回報說明）。已入庫的錯誤資料不在本單處理（回報裡說明修正後新爬到的會如何、舊資料是否會被重爬覆蓋）
- **設計依據**：`docs/development-spec.md` 2.1「識別碼與時間」（推文時間取文章年份，推文月份小於文章月份時年份 +1）；#179。規則本身若有漏洞需要改，同 PR 更新 2.1
- **相依**：無
- **負責檔案**：
  - `src/radar/collector/parsers/ptt.py`
  - `tests/unit/collector/parsers/`
  - `tests/fixtures/ptt/`（新增重現用 fixture）
  - `docs/development-spec.md`（只限 2.1 推文年份那一行）
  - `tests/unit/acceptance/comment-year-infer/`
- **禁區**：不改 ingest、DB schema、ClickHouse migration；不刪改已入庫資料
- **驗收測試**：
  - `tests/unit/acceptance/comment-year-infer/`
- **驗收條件**：
  - [ ] 重現測試：文章 12 月、推文 1 月 → 隔年；文章 1 月、推文 1 月 → 同年；推文月份大於文章月份（例：文章 10 月、推文 11 月）不會被推到未來一年以上；任一 `commented_at` 不晚於爬取時間太多（容許值由 worker 依 2.1 決定並寫進測試）
  - [ ] 推文時間格式異常時不會產生未來時間（回 NULL 或依規則處理，並記 log）
  - [ ] 驗收測試、`make check` 通過；`grep -rn "TODO(comment-year-infer)" src tests` 沒有結果
- **驗證指令**：`uv run pytest tests/unit/acceptance/comment-year-infer tests/unit/collector`；`make check`
- **回報檔**：`reports/comment-year-infer.json`

## 執行資訊（task.py 產生）

- Issue：#207
- 分支：`fix/comment-year-infer`（從 develop 開出）
- 工作目錄：`.worktrees/comment-year-infer`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-29

### reports/comment-year-infer.qa.md

FAIL a8432d6

# QA comment-year-infer（PR #211）

## 實際執行
- `uv run pytest tests/unit/acceptance/comment-year-infer tests/unit/collector -q` -> `165 passed in 0.37s`
- `uv run pytest tests/unit -q` -> `1433 passed in 15.19s`
- `uv run ruff check .` -> All checks passed；`ruff format --check .` -> 296 files already formatted
- `grep -rn "TODO(comment-year-infer)" src tests` -> 無結果
- pre-commit 未另跑（sandbox 內 verifier 不改檔，ruff 已過）

## 逐條驗收
1. 重現測試（12 月/1 月跨年、1 月同年、10 月推 11 月不被推未來、不晚於爬取時間+1 天）：PASS。驗收測試 test_comment_year_acceptance.py 涵蓋，容許值 1 天寫在測試與 2.1。
2. 格式異常不產生未來時間：行為 PASS（parametrize 異常字串、02/30、02/29、空字串、單筆壞不影響他筆）。**但「並記 log」沒有任何測試**（見 FAIL-1）。
3. 驗收測試與單元測試通過、無 TODO：PASS。

## 特別檢查
- test_ptt_post.py 跨年測試：只改 crawled_at 為 2027-01-02（原 2026-10-07 早於文章 2026-12-31，新上界會把推文判為未來）。斷言不變（12/31 23:55 -> 2026-12-31T15:55Z、01/01 00:05 -> 2026-12-31T16:05Z）；若拿掉跨年 +1 年，結果會變 2026-01-01，測試仍會失敗，所以仍驗到原本跨年行為。PASS。
- 開發規格 2.1 新規則（超過爬取時間 1 天退一年、不早於文章時間、仍不合理回 NULL 並記 log）與 `_bounded_comment_time` 一致（上界 `crawled_at + 1 天`、`post_created_at <= earlier`、ValueError(2/29) 回 None、log.warning）。PASS。
- 寫死設定值：無（1 天容許值為常數 _FUTURE_TOLERANCE，非環境設定）。

## FAIL
### FAIL-1 記 log 的行為沒有測試
重現：`grep -rn "caplog\|log" tests/unit/collector/parsers/test_ptt_comment_bound.py tests/unit/acceptance/comment-year-infer` 無任何 log 斷言。把 `_bounded_comment_time` 內 `log.warning(...)` 刪掉，所有測試仍會通過。驗收條件 2 與 2.1 都寫「並記 log」，此行為未被測試保護。test_future_time_before_post_becomes_none、test_feb_29_cannot_step_back_becomes_none 只驗回 None。
補測方向：用 loguru handler（或專案 radar.common.log 的測試慣例）攔截，斷言回 None 時有一筆 WARNING，且回正常值／退一年時沒有 WARNING；另可經 parse_post_page 驗證一次。

## 非阻擋備註（不列為 FAIL）
- 規則限制：文章 2025/10、真實推文 2026/11 時，推文月份不小於文章月份，補成 2025/11（早於爬取時間，不是未來），為錯誤但無法偵測；退一年也只是推測。已在 worker 回報提到根因，建議 2.1 註明此限制。
- NULL 60 則原因 worker 未能判定（無樣本），需從原始 HTML 抽樣；舊資料需另行回填。

## 追加 2026-10-29

### reports/comment-year-infer.review.md

REQUEST_CHANGES b78037e

# Review comment-year-infer（PR #211）

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| 改到的檔案都在負責檔案內（ptt.py、tests/unit/collector/parsers/、2.1 一行、驗收目錄） | OK；禁區（ingest、schema、migration、已入庫資料）未碰 |
| 驗收測試目錄只有 qa 的 `test(comment-year-infer)` commit（d7433af、09806a3、b78037e） | OK |
| 寫死設定值 | 無；1 天容許值是常數，屬於規則，不是部署設定 |
| 驗收條件 1～3 與測試 | 跨年／同年／11 月、格式異常、記 log 都有測試；qa 第二輪突變驗證過 log 測試 |
| test_ptt_post.py 只改 crawled_at | OK，斷言未放寬（qa 已驗） |
| 2.1 新規則是否合理 | **不合理**：「退一年」那段永遠不會發生，見問題 1 |

## 問題

1. `src/radar/collector/parsers/ptt.py:199-205`、`docs/development-spec.md:126`、`tests/unit/collector/parsers/test_ptt_comment_bound.py:18` — 「退一年（不早於文章時間）」是走不到的分支，2.1 寫的是程式實際上不會有的行為。
   - 證明：`parse_comment_time`（`ptt_time.py`）只會給出文章年份（推文月份 ≥ 文章月份）或年份 +1（月份 < 文章月份），所以結果一定落在「文章當月 1 日（台北時間）」到「一年後的同一天」之間；退一年後一定早於文章時間，`post_created_at <= earlier` 永遠不成立。我窮舉了 3 年內的文章時間 × 5 種爬取延遲 × 12 個月 × 4 個日期，未來時間 201,666 筆，退一年成功 0 筆。
   - `test_future_time_steps_back_one_year_when_valid` 餵的是 `parse_comment_time` 產生不出來的輸入（文章 2025/10、推文 11 月會被補成 2025/11，不會是 2026/11），所以它測的是走不到的路徑。
   - 要怎麼改：刪掉退一年的分支（第 199-205 行與 `PTT_TZ` import），改成「晚於爬取時間 + 1 天 → 回 None 並 log.warning」；2.1 改成「…年份 +1；結果晚於爬取時間超過 1 天回 NULL 並記 log」；刪除 `test_future_time_steps_back_one_year_when_valid` 和 `test_feb_29_cannot_step_back_becomes_none`（2/29 的情況改成驗「未來時間回 None」即可）。驗收測試（含 `test_unreasonable_comment_time_logs_one_warning`）在這個改法下仍成立，不用改。
2. `reports/comment-year-infer.json` open_questions[0] — 推測的根因跟觀察到的資料對不起來。依問題 1 的範圍，「舊文章很久之後才被推」只會補成過去的時間，不會變成未來。觀察到的 2026-11～2027-09 比較像是推文時間**早於文章標頭時間**（例：修改或轉錄的文章，把舊推文帶進新文章；10 月的文章裡出現 9 月的推文會被 +1 年補成 2027-09，出現 11 月的推文會補成 2026-11）。
   - 要怎麼改：回報改寫成這個推測，並註明要從 PG／原始 HTML 抽 `commented_at` 在未來的推文確認（跟 NULL 的 60 則一起抽）。這類推文在修正後會變成 NULL；它們的真實時間其實能推回來（退一年、不限制不早於文章時間），要不要保留由 manager 決定是否另外開單，本單不做。

## 非阻擋

- 早於文章時間、但沒有落在未來的推文（例：10/20 的文章裡出現 10/05 的推文）不會被這條規則抓到，會照原樣保存；屬於上面推測的同一類資料，抽樣確認後一起處理。

manager 補充（review 問題 1 的「這類推文要不要保留真實時間」）：
- 先照 review 問題 2 從原始資料（PG／log／PTT fixture，不對真實 PTT 發請求）抽樣，確認未來時間推文的實際成因，並一起抽樣 NULL 的 60 則
- 若抽樣證實是「推文時間早於文章標頭時間」（修改／轉錄帶入舊推文），就保留真實時間：退一年且不加「不早於文章時間」限制，只要求結果不晚於爬取時間＋1 天；推不回來的才回 NULL 並記 log。抽樣不支持就照 review 原建議拿掉退一年分支
- 規格 2.1 照最後的實際行為寫；單元測試要用 parser 真的會產生的輸入
