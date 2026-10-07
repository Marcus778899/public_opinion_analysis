# PTT HTML fixtures

parser 測試只讀這裡的檔案，任何測試都不可對 PTT 發請求（CLAUDE.md）。

## 來源

2026-10-07 從 www.ptt.cc 抓取的真實頁面，**保留 HTML 結構，內容全部替換**：

- 使用者 ID → `user001`…、作者 → `author1 (測試暱稱)`
- 推文內容 → `測試推文N`、內文 → 固定的測試內文（含簽名檔）、標題 → 測試標題
- IP → `192.0.2.x`（RFC 5737 文件專用位址）

## 檔案

| 檔案 | 用途 | 除了替換內容外的人工修改 |
|---|---|---|
| `list_stock.html` | 列表頁：置底分隔線與置底公告 | 在分隔線前加入一列被刪除的文章、一列 `X3` 推文數 |
| `list_first_page.html` | 第一頁，「‹ 上頁」為停用狀態 | 無 |
| `post_normal.html` | 一般文章，推、噓、→ 三種推文 | 原文沒有噓，把兩則 → 改成噓 |
| `post_boom.html` | 爆文，含 `warning-box`（不是推文的 div.push） | 推文只保留前 190 則 |
| `post_ip_comments.html` | 推文時間前帶 IP | 無 |
| `post_cross_year.html` | 12/31 發文、01/01 的推文 | 由 `post_normal` 改時間 |
| `post_edited.html` | 推文間夾「※ 編輯:」行 | 由 `post_normal` 插入編輯行 |
| `post_no_header.html` | 標頭缺漏，以檔名 epoch 推算發文時間 | 由 `post_normal` 移除標頭 |
| `over18.html` | `/ask/over18` 確認頁 | 無（頁面本身沒有使用者內容） |
