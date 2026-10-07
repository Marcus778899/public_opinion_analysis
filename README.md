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

```bash
make up                 # Kafka（3 節點）+ Postgres；make up-debug 另外啟動 Kafka UI（:8089）
make migrate            # 建表
make topics             # 建立 Kafka topic（冪等）
make api                # 管理 API，文件在 http://localhost:8000/docs
make seed               # 另開終端機：建立 Gossiping、Stock、Tech_Job 三個看板

# 另開終端機啟動爬蟲與 ingest
uv run --env-file .env python -m radar.collector.crawler
uv run --env-file .env python -m radar.ingest.main

# 手動觸發一次爬取（Scheduler 完成前用這個方式）
curl -X POST localhost:8000/boards/Tech_Job/crawl
curl localhost:8000/status
```

`make down` 停止所有容器（資料保留在 volume）。

## 授權

[PolyForm Noncommercial License 1.0.0](LICENSE)：禁止商業用途。
