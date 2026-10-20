# Python 工具對照

| 用途 | 建議 | 備註 |
|---|---|---|
| 環境 | `uv` 或 `venv` + `requirements.txt`（版本釘死） | worktree 共用主目錄的 `.venv`，相依變了要 `check_env.py setup` |
| 測試 | pytest；整合測試在 compose 的 `test` 服務裡連 compose 的 DB | FastAPI 用 `TestClient`／`httpx.AsyncClient` 打真的 app |
| 覆蓋率 | pytest-cov（coverage.py） | |
| lint／格式 | ruff（lint + format）；型別檢查 mypy 或 pyright | |
| migration | Alembic（SQLAlchemy）、Django migrations | Alembic 每支都寫 `downgrade()` |
| 驗證 | Pydantic model 在邊界；不要把 dict 一路傳進商業邏輯 | |
| 相依稽核 | CI 的 osv-scanner 會讀 `requirements.txt`、`poetry.lock`、`uv.lock` | 本機可用 `pip-audit` |

## `make coverage`（Cobertura XML 寫到 `coverage-reports/`）

```make
coverage:
	.venv/bin/pytest --cov=app --cov-report=xml:coverage-reports/python.xml -q
```

`--cov=app` 指定原始碼目錄，沒被 import 的檔案也會列進報告（0%）。後端在子目錄（例 `backend/`）時從 repo 根目錄跑，或確認報告的 `<source>` 是絕對路徑。
