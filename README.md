# 即時輿情雷達

追蹤 PTT 等社群上的話題，在討論開始發酵的前幾分鐘偵測並通知，同時提供情緒分析與話題摘要。

## 文件

- [設計文件](docs/realtime-sentiment-radar-design.md)
- [開發流程規格](docs/development-spec.md)

## 開發環境

需要：Python 3.12、[uv](https://docs.astral.sh/uv/)、Docker、pre-commit

```bash
uv sync                 # 建立 .venv 並安裝相依套件
cp .env.example .env    # 填入本地設定
pre-commit install      # 啟用 commit 前檢查
make test               # 單元測試（make test-int 為整合測試，需要 Docker）
```

## 本機執行

**整套以 docker-compose 執行**（會對真實 PTT 發請求）：

```bash
make up-app             # Kafka（3 節點）+ Postgres + CDC + ClickHouse + api / scheduler / crawler ×3 / ingest
make seed               # 建立 Gossiping、Stock、Tech_Job 三個看板，Scheduler 30 秒內開始爬取
curl localhost:8000/status
make down               # 停止（資料保留在 volume）
```

**開發時只啟動基礎設施**，服務在本機執行：

```bash
make up && make migrate && make topics && make ch-migrate && make connector
make api                                                    # 另開終端機
uv run --env-file .env python -m radar.collector.scheduler  # 另開終端機
uv run --env-file .env python -m radar.collector.crawler    # 另開終端機
uv run --env-file .env python -m radar.ingest.main          # 另開終端機
make seed
```

**端到端測試**（假 PTT 伺服器、獨立的資料 volume，不碰開發資料也不連真的 PTT）：

```bash
make e2e-up && make e2e && make e2e-down
```

## 授權

[PolyForm Noncommercial License 1.0.0](LICENSE)：禁止商業用途。
