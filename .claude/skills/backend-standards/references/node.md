# Node／TypeScript 工具對照（後端，或前端的覆蓋率）

| 用途 | 建議 | 備註 |
|---|---|---|
| 測試 | Vitest 或 Jest；HTTP 用 supertest；整合測試在 compose 的 `test` 服務裡連 compose 的 DB | |
| 覆蓋率 | Vitest／Jest 內建（istanbul 或 v8），reporter 用 `cobertura`（不可用 lcov：會跟後端的 XML 衝突） | 要設 `coverage.include`（例 `['src/**']`），沒被 import 的檔案才會列進報告 |
| lint／格式 | ESLint + Prettier；`tsc --noEmit` 型別檢查 | |
| migration | Prisma Migrate、Knex、TypeORM migrations | 都要能 down |
| 驗證 | zod 等 schema 在邊界 parse；TypeScript 型別不等於執行期驗證 | |
| 相依稽核 | CI 的 osv-scanner 會讀 `package-lock.json`、`pnpm-lock.yaml`、`yarn.lock` | |

## `make coverage`（Cobertura XML 寫到 `coverage-reports/`）

```make
coverage:
	npx vitest run --coverage --coverage.reporter=cobertura --coverage.reportsDirectory=coverage
	mkdir -p coverage-reports
	cp coverage/cobertura-coverage.xml coverage-reports/node.xml
```

Jest：`--coverageReporters=cobertura`。前後端都有就各產一份 XML 放進 `coverage-reports/`，CI 一起讀，不用合成一個數字。
