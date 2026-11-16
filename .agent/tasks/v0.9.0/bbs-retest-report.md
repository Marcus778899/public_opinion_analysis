# 派工單 bbs-retest-report

- **類型**：docs
- **負責**：backend
- **目標**：依補實驗結果把 `docs/reports/bbs-spike.md` 更新成最終建議（7.31 G-5），並在開發規格 7.31 G 與「後續階段」13 補結論
- **背景**：
  - 甲方 11-10 晚跑完 retest：run `20261110T124120Z`，輸出 `data/spike/bbs-retest/`（不進 repo）；`summary.json` 由 manager 以 `summarize-retest --hot-concurrent-p90 33 --rules unconfirmed` 算出：R2 207 則／4 篇、`excluded` 空、p50(`E`) 52.7 秒，網頁版 315.1 秒；`n_max` 4、全量 9 條；連線 tested 3／proven 3、無停止；混合 12 篇占 p90 36%；三項成立、`recommend: true`
  - ledger：A 12:41、B 13:21、C 13:31（UTC）3 次登入全成功；R2 在最短 40 分鐘結束；M 沒有多重登入警告、沒有被踢
  - 選取：甲方以 ClickHouse 篩候選（50 分鐘內、推減噓 ≥ 10、最熱 4 篇）每 5 分鐘交工具登入前檢查（網頁版即時 ≥ 30、≤ 60 分鐘），20:05～20:36 被拒 7 次、20:41 通過；11-09 晚因 ClickHouse 篩 ≥ 30 湊不到 4 篇沒啟動、沒用登入額度
  - 站規仍未確認（`docs/research/bbs-rules.md`），建議要附「導入前甲方確認站規」；k=3 只證實能同時連線，沒量多條同時輪讀的延遲（G-5）
  - 網路同第一次（家用、與開發爬蟲同一對外 IP）；第一次報告第 3 節 IP 評估沿用並補這次觀察（網頁版失敗以 events.jsonl 為準）；D-050 的改回選填不在本單
- **設計依據**：`docs/development-spec.md` 7.31 G（G-2、G-3、G-3a、G-5）與 F 格式；D-047～D-051
- **相依**：無
- **負責檔案**：
  - `docs/reports/bbs-spike.md`
  - `docs/development-spec.md`（只動 7.31 G 的結論與「後續階段」13）
- **禁區**：不改程式；不連 PTT；不重算或改寫 `summary.json`；文件不寫推文內容、PTT 使用者 ID、帳號；數字只取自 `data/spike/bbs-retest/` 的檔案與本單背景
- **驗收測試**：無
- **驗收條件**：
  - [ ] 報告第一行改成最終建議（依 G-5：三項都成立 → 建議導入混合方案，前 4 × k 篇走 BBS、其餘網頁版；附「導入前甲方確認站規」；決定歸甲方）
  - [ ] 新增「補實驗」一節，逐條列 R1、R2、R3 的判定與數字，含與網頁版比較、`N_max`、全量連線數、12 篇占 p90 比例、k=3 為推算的限制；全文 ≤ 200 行
  - [ ] 依結果重算需要的連線數並寫明口徑（R2 平均讀取，全程平均附註）
  - [ ] 第一次實驗段落保留，與最終建議矛盾的句子改成引用補實驗（例：舊建議、第 7 節導入前工作）
  - [ ] 7.31 G 與「後續階段」13 補結論（引用報告，不重寫）
- **驗證指令**：`make check`；`grep -rniE "PTT_BBS_(USERNAME|PASSWORD)=." docs` 沒有結果；`wc -l docs/reports/bbs-spike.md` ≤ 200
- **回報檔**：`.agent/reports/bbs-retest-report.json`

## 執行資訊（ae task 產生）

- Issue：#336
- 分支：`docs/bbs-retest-report`（從 develop 開出）
- 工作目錄：`.worktrees/bbs-retest-report`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
