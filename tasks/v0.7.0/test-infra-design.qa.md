PASS 34535f6

# test-infra-design 驗證（merge 後，PR #87）

HEAD 34535f6；develop 為 e3a5d48，是 HEAD 的祖先（`git merge-base --is-ancestor develop HEAD` 成立）。

## 對照 manager 要求
- develop...HEAD 只改 docs/development-spec.md：`git diff develop...HEAD --name-only` 只有該檔；`--stat`：94 insertions, 1 deletion。
- 內容都是本單：增加三處，皆為 7.26 相關：5 章整合列加「規劃改為 compose test 服務，見 7.26」（唯一的 1 行刪除，即此列改寫）、進度表新增 7.26 一列、新增 7.26 整節。
- develop 的 7.25 沒被動：`git diff develop HEAD | grep -c '^-[^-]'` 只有 1（上述整合列），7.25（line 1009～1100）無任何刪除；進度表 7.25 一列（line 364）保留，7.26 在其後（365）；7.25 小節 grafana.xml、from_env、派工順序 `dashboard-grafana-infra` 都還在。
- 無衝突標記：`grep -nE '^(<<<<<<<|=======$|>>>>>>>)' docs/*.md` 無輸出。
- 7.26 與 D-015 一致：decisions.md D-015 決定 B（加 pytest-xdist dev 相依、不用付費 runner），影響「7.26 做法第 15 項、test-infra-fast-waits」；7.26 做法 15、隔離表、派工 2（uv.lock、pyproject.toml 加 pytest-xdist，D-015）、風險表都對得上。
- 風險表 users.d 列：7.25 確實寫 `infra/clickhouse/users.d/grafana.xml` 以 `from_env` 讀密碼，列內描述正確；目前 develop 的 users.d 只有 radar.xml（grafana.xml 尚未實作，列為設計預期，合理）。`infra/clickhouse/config.d/named_collections.xml` 確實用 `kafka_1:29092,kafka_2:29092,kafka_3:29092`，與做法 6 一致。

## 驗收條件
1. 用法（用法表、與開發／e2e 關係 #41）與 CI 加速方案（量測表附 run 39381652748 各檔秒數、步驟耗時 run 39374102085）：成立。
2. 派工順序表有 task_id、負責、負責檔案、驗收測試目錄（兩張）：成立。
3. 需調查／待決定／自行決定在 reports/test-infra-design.json 的 open_questions 分列（需調查：無；待決定：新相依已由 D-015 定案；自行決定：做法 1～14）：成立。

## 備註（非 FAIL）
- 負責檔案另含設計文件，未改動，合理。
- Makefile 已有 `test-int`（`uv run pytest tests/integration`）；7.26 派工 1 寫「Makefile（test-int）」是改寫它，用法表的「人在主目錄」列描述的是改後行為，一致。
- 未執行程式測試：本單為純文件，驗收測試「無」。run 連結的實測數字（CI log）未重新查證，沙箱無 gh 憑證，只做文件內部一致性檢查。
