PASS 4993a7b

# QA comment-year-infer（PR #211，第三輪）

## 實際執行（.worktrees/comment-year-infer）
- `uv run pytest tests/unit/acceptance/comment-year-infer tests/unit/collector -q` -> `168 passed in 0.39s`
- `uv run pytest tests/unit -q` -> `1436 passed in 15.16s`
- `uv run ruff check .` -> All checks passed；`ruff format --check .` -> 296 files already formatted
- `grep -rn "TODO(comment-year-infer)" src tests` -> 無結果

## 驗收測試未被改動
`git log -- tests/unit/acceptance/comment-year-infer` 只有 qa 的三個 test commit（d7433af、09806a3、b78037e）；`git diff b78037e HEAD -- tests/unit/acceptance` 無差異。

## 規格 2.1 與實作一致
2.1 新規則：補成隔年且晚於爬取時間 +1 天 -> 退回文章年份（退後仍須不晚於爬取時間 +1 天）；其餘未來時間回 NULL 並 log；PTT 截斷缺 HH:MM 為 NULL。
`_bounded_comment_time`：`when <= crawled_at+1d` 原樣；`local.year > 文章台北年` 才嘗試退一年，退後 `<= crawled_at+1d` 才採用；2/29 ValueError 與其餘情況皆 log.warning 回 None。逐項一致。走不到的「不早於文章時間」分支已刪（review 問題 1 已解）。

## 單元測試輸入是 parser 真的會產生的
`parse_comment_time` 只產生文章年或年+1。test_ptt_comment_bound.py：2027-05-01（文章 10 月、推文 05/01 -> +1）退 2026-05-01；2026-11-05（11 月 >= 10 月，同年）回 None；2028-02-29（文章 2027/10、推文 02/29 -> +1 年閏年）退一年 ValueError 回 None；退後仍未來回 None。皆為可產生輸入。test_ptt_post.py 跨年測試僅把 crawled_at 改為 2027-01-02，斷言不變，拿掉 +1 年仍會失敗。

## 抽樣成因證據
查開發 PG（`docker compose ... exec postgres psql`，未對 PTT 發請求）：
- Gossiping.M.1793238717.A.B3C（epoch = 2026-10-29 01:51 UTC，posts.created_at 相符）floor 1-5 commented_at = 2027-02-14 19:43～19:46 UTC，即台北 02/15 03:43 +1 年，與 worker 回報吻合
- HatePolitics.M.1793061234.A.EA9（文章 2026-10-27）floor 1 = 2027-05-01 01:35 UTC，即 05/01 09:35 +1 年，吻合
- 其餘 epoch 對照文章日期（Gossiping...1793178844 = 10/28、...1792171863 = 10/16、Stock...1793101231 = 10/27）與回報一致
成因「推文時間早於文章標頭時間（轉錄／修改帶入舊推文），被 +1 年」成立。NULL 的成因（PTT 截斷長推文缺 HH:MM）我未重驗原始 HTML，但已寫進 2.1，符合 PTT 原始資料本來沒有時間的分類。

## 寫死設定值
無（1 天容許值為規則常數）。

## 非阻擋備註
- 推文月份 >= 文章月份而落在未來者（例 10/16 文章中的 11/09）回 NULL，真實年份（可能前一年）無法還原；回報已說明為驗收測試限制，由 manager 決定是否另開單。
- 早於文章時間但未落在未來的帶入推文照原樣保存；舊資料需重爬或回填。
