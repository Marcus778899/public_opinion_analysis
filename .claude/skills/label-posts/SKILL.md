---
name: label-posts
description: 以 Claude 當第二標註者，依 docs/labeling-guideline.md 標註一批 PTT 文章（S3-03 交叉比對）。使用者說「標註一批文章」「/label-posts」時使用。
---

# 標註一批 PTT 文章

Claude 在這裡扮演**第二標註者**（`labeler = claude-sonnet-manual`），結果用來和主要標註者交叉比對（開發規格 7.11）。

## 步驟

1. **匯出**：`uv run --env-file .env python -m radar.ml.labeling.manual export --size 50`
   - 產生 `data/manual/batch-<時間>.jsonl`，每行一篇：`post_id`、`board`、`title`、`content`（已依 `LABEL_MAX_CHARS` 截斷）
   - 印出 `exported nothing` 代表主要標註者標過的文章都已手動標完，結束並告知使用者
2. **讀準則**：完整讀 `docs/labeling-guideline.md`（規則與範例），每一批都重新讀，不憑記憶
3. **標註**：逐篇讀 batch 檔，依準則判斷，寫到同目錄的 `batch-<時間>.out.jsonl`，每行一篇：
   ```json
   {"post_id": "Stock.M.1759730000.A.1B2", "sentiments": [{"target": null, "polarity": "negative"}, {"target": "台積電", "polarity": "negative"}]}
   ```
   - 恰好一筆 `target: null`（整篇）；對象最多 5 個、不重複、只列作者有評價的
   - `polarity` 只能是 `positive`、`negative`、`neutral`
   - **獨立判斷**：不要去查 ClickHouse 裡主要標註者的結果，否則交叉比對失去意義
   - 拿不準的不要硬標：略過該篇（不寫進 `.out.jsonl`），並在回報中列出 `post_id` 與原因
4. **匯入**：`uv run --env-file .env python -m radar.ml.labeling.manual import data/manual/batch-<時間>.out.jsonl`
   - 任何一行格式錯誤整批不送，依錯誤訊息修正後重跑
5. **回報**：標了幾篇、略過幾篇（附原因）、整篇情緒的分布、遇到準則沒涵蓋的情況（建議如何修準則）

## 注意

- 一次一批（預設 50 篇），避免一次讀太多內文；使用者要多批時逐批重複
- 只讀標題與內文，batch 檔裡沒有推文，也不要另外查
- 不修改 `docs/labeling-guideline.md`；準則需要改時只提出建議，由使用者決定
