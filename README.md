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
uv run pytest           # 執行測試
```

## 授權

[PolyForm Noncommercial License 1.0.0](LICENSE)：禁止商業用途。
