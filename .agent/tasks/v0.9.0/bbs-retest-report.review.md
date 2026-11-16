APPROVE 4fbc17a

# Review：PR #337 bbs-retest-report

對照：派工單 `.agent/tasks/bbs-retest-report.md`、開發規格 7.31 G（G-2、G-3、G-5）、布告欄驗收條件；數字逐項對 `data/spike/bbs-retest/20261110T124120Z/`（`summary.json`、`events.jsonl`、`reads.jsonl`、`connections.json`、`clock.json`、`meta.json`）與 `data/spike/bbs-retest/ledger.jsonl`。

## 範圍

- 只改 `docs/reports/bbs-spike.md`、`docs/development-spec.md`（`git diff develop...4fbc17a --name-only`），沒有改程式
- CI：Check、Integration Test、Security 都 pass
- 報告 145 行（≤ 200）
- `grep -rniE "PTT_BBS_(USERNAME|PASSWORD)=." docs` 只命中 `docs/uat/v0.9.0.md:15`，那是 uat 檔裡寫的 grep 指令文字，不是帳密值，也不是這張單的檔（worker 已列進 open_questions）
- 報告沒寫 post_id、推文內容、使用者 ID、帳號

## 驗收條件

| 條件 | 結果 |
|---|---|
| 第一行是最終建議（G-5 三項成立 → 混合方案、前 4 × k 篇走 BBS、導入前甲方確認站規、決定歸甲方） | 符合 |
| 「補實驗」一節：R1／R2／R3 判定與數字、與網頁版比較、`N_max`、全量連線數、12 篇占 p90 比例、k=3 是推算的限制 | 符合 |
| 重算連線數並寫口徑（R2 平均讀取，另附全程平均） | 符合：5.25 秒／82 次 → `N_max` 4；全程 5.34 秒／114 次也是 4；全量 ⌈33/4⌉ = 9 |
| 保留第一次實驗的段落，矛盾的句子改成引用補實驗 | 符合：第 1 節標題、混合方案判定、作廢那段、第 4 節同時登入數與方案 B、第 7 節標題都改成引用 |
| 7.31 G 與後續階段 13 補結論，引用報告不重寫 | 符合 |

## 數字核對（全部對得上）

- R2：207 則、4 篇、p50 `L`/`E`/`U` 22.7/52.7/82.7、`excluded` 空；各篇 102/37/37/31（報告寫「102 則來自 1 篇、其餘 31～37」）
- 網頁版 p50(`E`) 315.1、配對差 p50 262.8、未出現 0、比對不上 0；時鐘偏差 0.43
- reads：R2 82 次、M 32 次全部 ok（共 114）；R2 每篇 20～21 次
- connections：tested 3／proven 3／stop_reason null；`stop_triggered` false；mixed 12 篇、占 p90 0.364
- ledger：A 12:41:29、B 13:21:44、C 13:31:49（UTC），間隔 ≥ 10 分鐘；第一次 ledger 2 筆 → 累計 5 次登入
- 選取：4 篇發文距 run 開始 27～43 分鐘（≤ 60），Gossiping 2、Stock 2
- `events.jsonl` 只有推文事件（第一次的 run 也一樣），報告寫「網頁版失敗看不出來、未驗證」，沒有亂猜

## 不擋合併的觀察（不用改）

1. `docs/development-spec.md` 在 7.31 第一次結論的後面加了一行「（以上是第一次實驗的結論；最終建議見 G 的結論。）」，不在 G 節裡，超出派工單「只動 7.31 G 的結論與 13」的字面範圍。這行只是引用，用來避免文件前後矛盾（CLAUDE.md 文件同步），可以接受；manager 要不要追認自己決定。
2. 「22.5 為輪讀間隔平均」是設計值（20＋0～5 秒）；用 reads.jsonl 算出來的實際間隔約 24.2 秒，套進去 `N_max` 還是 4，結論不變。跟第一次報告用的口徑一樣。
3. 「UTC 12:41～13:32」是 BBS 的時段；網頁版尾段讀到 13:52。只是描述，不影響判定。
