# Go 工具對照

| 用途 | 建議 | 備註 |
|---|---|---|
| 測試 | 標準 `testing` + table-driven；HTTP 用 `httptest`；整合測試在 compose 的 `test` 服務裡連 compose 的 DB | 加 `-race` 跑 |
| 覆蓋率 | `go test -coverprofile`，用 gocover-cobertura 轉成 XML | 用 `-coverpkg=./...`：跨套件呼叫才算得到，沒有測試的套件也會列進報告 |
| lint／格式 | `gofmt`、`go vet`、golangci-lint | |
| migration | golang-migrate、goose | 每支都有 down |
| 錯誤 | `fmt.Errorf("...: %w", err)` 包裝、`errors.Is／As` 判斷；邊界統一轉成錯誤格式 | 不要 `panic` 當一般錯誤處理 |
| context | 每個請求、DB、外部呼叫都傳 `context.Context`，設 timeout | |
| 相依稽核 | CI 的 osv-scanner 會讀 `go.mod`；本機可用 `govulncheck ./...`（只報實際呼叫到的漏洞） | |

## `make coverage`（Cobertura XML 寫到 `coverage-reports/`）

```make
coverage:
	go test ./... -coverpkg=./... -coverprofile=cover.out
	mkdir -p coverage-reports
	go run github.com/boumenot/gocover-cobertura@v1.5.0 < cover.out > coverage-reports/go.xml
```

`cover.out` 加進 `.gitignore`。module 在子目錄（例 `backend/`）時，在子目錄跑，輸出路徑改成 `../coverage-reports/go.xml`。
