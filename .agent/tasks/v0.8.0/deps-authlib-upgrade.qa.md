PASS 70e6f5c

# 驗證 deps-authlib-upgrade（PR #185）

## 1. uv.lock 只變 authlib，版本 ≥ 1.9.1
`git diff origin/develop...HEAD`：只動 `uv.lock`，3 行增、3 行刪，僅 authlib 區塊（1.8.0 -> 1.9.1，sdist／wheel URL 與 hash 同步）；依賴 cryptography、joserfc 未變；pyproject.toml 未改。

```
$ uv sync
Resolved 93 packages in 39ms
Checked 90 packages in 38ms
$ uv run python -c "import authlib;print(authlib.__version__)"
1.9.1
```

## 2. osv-scanner
本機無 osv-scanner，依派工單以 PR #185 CI 為準（`gh pr checks 185 --watch`）：

```
Check             pass  51s
Integration Test  pass  2m44s
Security          pass  37s
```

## 3. make check
```
tests/unit/test_smoke.py ..................................... [100%]
============================= 1348 passed in 4.22s =============================
```
（lint 與單元測試在 make check 內，結束碼 0；CI Check 同為 pass。）

## 邊界與其他
- 本單只改 lock，無程式碼變動，沒有寫死設定值或 TODO(deps-authlib-upgrade) 可查。
- 整合測試（含 avro／schema registry）在 CI 通過。
- 問題數量：0
