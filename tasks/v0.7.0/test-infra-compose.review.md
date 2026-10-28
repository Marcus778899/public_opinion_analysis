APPROVE 7a75691

# Review PR #95 test-infra-compose 第 3 輪（commit 7a75691）

對照：派工單 `tasks/test-infra-compose.md`（含範圍更正與上輪 review 追加）、開發規格 7.26、上一輪 review（efe6826，REQUEST_CHANGES 2 條）。

## 上輪必修

| # | 結論 | 依據 |
|---|---|---|
| 1 `development-spec.md` 7.26 風險表 users.d 一列 | 已解 | 第 1210 行改成「只單檔掛 `named_collections.xml`、`radar.xml`（做法 7），不會載入 `grafana.xml`…由 `dashboard-grafana-infra` 在 `compose.yaml` 加掛該檔並給測試用的固定值（不讀 `.env`）」；與做法 7（第 1150 行）一致。7.25 第 1076 行「同 7.26 風險表 users.d 一列」引用的是「固定值、不讀 `.env`」，仍然成立 |
| 2 第 1180 行記憶體估計 | 已解 | 改成「每套實測尖峰約 1.4 GiB」；`grep "1.5～2\|後合併的一方"` 只剩第 1182 行實作補充裡的「原估 1.5～2 GB 偏高」，屬實測記錄，不是重複的估計 |

## 本輪變更

- `git diff efe6826..7a75691`：只改 `docs/development-spec.md` 兩行（上表兩處），沒有程式、測試、compose、CI 變更；第 1～2 輪已核可的檢查結果（compose 做法 1～12、conftest 重置防護、範圍、testcontainers 移除）不受影響，沿用 `efe6826` 一輪的結論。
- PR 檔案清單與上輪相同（20 個，都在更正後的負責檔案內）；PR head = `7a75691`，與 worktree 一致。
- 沒有新問題。

## CI（run 39395994646）

- Check pass（42s）、Security pass；Integration Test 寫本檔時仍 pending。本輪只改文件，上輪同樣程式碼的 Integration Test 已過（run 39394150949，`1201 passed`），合併前仍以這次 run 綠燈為準。

## 仍成立的建議（不阻擋，見上輪；交給 `test-infra-fast-waits`）

- 測試 Kafka 改用不同的 `CLUSTER_ID`，重置前比對 `cluster_id`，比主機允許清單可靠。
- `CLAUDE.md:86` 仍提 testcontainers（禁區，已在回報 open_questions）。
