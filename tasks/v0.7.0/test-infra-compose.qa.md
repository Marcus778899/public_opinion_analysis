PASS 7a75691

# QA test-infra-compose 第 3 輪（PR #95，commit 7a75691）

本輪只驗文件修正；程式未變，其餘驗收條件沿用第 2 輪（efe6826 PASS）。

## 1. efe6826..7a75691 只動兩處

```
$ git diff efe6826 7a75691 --stat
 docs/development-spec.md | 4 ++--
 1 file changed, 2 insertions(+), 2 deletions(-)
```
程式、compose、ci.yml、測試皆未變，故第 2 輪對它們的驗證仍有效。

## 2. review 兩個問題

- 必修 1（7.26 風險表 users.d 列，spec 第 1210 行）：已改為「compose 的 clickhouse 只單檔掛 named_collections.xml、radar.xml（做法 7），不會載入 grafana.xml，缺環境變數不會啟動失敗；需要唯讀帳號的測試由 dashboard-grafana-infra 在 compose.yaml 加掛該檔並給固定測試值（不讀 .env）」。對照 `compose.yaml:65-66` 確實只單檔掛這兩個檔，內容一致。已解。
- 必修 2（第 1180 行）：「實測後回寫」已刪（`grep -n 實測後回寫` 無結果），改為「每套實測尖峰約 1.4 GiB」，與下方實作補充的實測一致，同一件事兩處數字不矛盾（實作補充另說以 1.5 GB 計）。已解。

## 3. 本輪重跑（worktree）

```
$ PYTHONPATH=src uv run --no-sync pytest tests/unit -q
1066 passed in 3.10s
$ uv run --no-sync ruff check .
All checks passed!
$ grep -rn "TODO(test-infra-compose)" src tests
（無輸出）
```

## 4. docker

`docker compose -f compose.yaml config -q` 未帶 `--env-file .env` 時回 `required variable KAFKA_VERSION is missing`（預期，agent 不可讀 .env）；沒有重跑容器整合測試，依第 2 輪方式記錄、不判 FAIL。依據：第 2 輪 PASS、CI run 39394150949（1201 passed）；本輪無程式變更。

## 問題數量：0
