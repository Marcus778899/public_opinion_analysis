APPROVE a604ab1

PR #339（chore/bbs-env-optional），head `a604ab190b01060e444a9b6a80c5d80323900b3b`。

## 檢查項目

| 項目 | 結果 |
|---|---|
| 改到的檔案都在負責檔案內 | 是：`.env.example`（只動 PTT BBS 段）、`docs/development-spec.md`（只動 7.31 G-6「小號帳密」那一列）、兩個驗收測試檔（qa 的 commit 328b3e5） |
| 禁區 | 沒動 `tools/bbs_spike.py`、compose、check-env 工具 |
| 驗收條件 1 | `.env.example` 兩行改成 `# PTT_BBS_USERNAME=`、`# PTT_BBS_PASSWORD=`，沒有值；段落標題改成「選填，D-050」，不再引用 D-046；符合 D-009 選填寫法 |
| 驗收條件 3 | G-6 列寫明依 D-050 改回選填、`bbs-env-isolation` 不做（留 backlog） |
| 寫死設定值、密鑰 | 沒有；測試用的是假值 `x_user`／`x_pass`，只用 monkeypatch |
| 程式行為 | 沒改；`load_credentials()`（tools/bbs_spike.py:801）缺值或空字串會 `SystemExit`，訊息只列變數名，新驗收測試有涵蓋（全缺、缺一、空字串、訊息不含值） |
| 驗收測試是否真的測到驗收條件 | 是：註解且無值、沒有未註解的 `PTT_BBS_` 行、段落引用 D-050 不引用 D-046、工具拒絕登入；舊測試已依 D-050 改寫 |

## 實際執行

- `uv run pytest -q tests/unit/acceptance/bbs-env-optional tests/unit/acceptance/bbs-spike-tool` → `88 passed`
- `make check` → `2246 passed in 142.92s`
- `grep -nE "^PTT_BBS_" .env.example` → 沒有結果（rc=1）
- `gh pr checks 339`：Security pass；Check、Integration Test 撰寫時仍 pending

## 觀察（不擋合併，給 manager）

- `docs/development-spec.md:2162` 待決定 G-a 列仍是提問形式（推薦 A）；D-050 已定案，可在之後的設計單改成「已決定 D-050」。本單負責範圍只限 G-6 列，所以不算偏離。
- `README.md:141` v0.9.0 歷史列寫「`PTT_BBS_*` 改必填（D-046）」，屬歷史紀錄；要不要補 D-050 由 manager 決定（README 歸 manager）。
