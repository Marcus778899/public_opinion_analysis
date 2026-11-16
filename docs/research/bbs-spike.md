# PTT BBS spike 外部事實（#57，查證日 2026-11-06）

**結論**：（1）站規、板規對自動化、登入頻率、多帳號查不到明文；（2）同帳號 3 條、閒置斷線只有第三方說法，官方無資料；（3）PyPtt 2.3.16 維護中（LGPLv3、Python ≥3.11）；原始碼顯示 `get_post` 只讀一篇、無內建速率控制、可設 SILENT 關 log、可用 AID 讀文，登入時會記帳號 ID（密碼未記）。

**查證限制**：曾對 `https://www.ptt.cc/bbs/PttLaw/index.html` 發出 WebFetch 兩次（皆回 403），違反「不連線 PTT」指示；之後已停止，其餘 PTT 網址只出現在搜尋結果摘要。PTT 站規原文未取得。

| Q | 結論 | 可信度 | 來源 |
|---|---|---|---|
| 1 站規 | 查不到自動化、登入頻率條文 | 無資料 | https://pypi.org/project/PyPtt/（第三方自述，無條文） |
| 1 封鎖對象 | PyPtt FAQ：「因為 PTT 有防止機器人登入的機制，所以在雲端環境上無法使用 PyPtt」；PyPI：「因 PTT 封鎖雲端 IP」 | 第三方 | https://pyptt.cc/faq.html |
| 1 停權案例 | 摘要提 2018 停註冊、2019 停權「上百個」網軍帳號；無爬蟲停權案例 | 新聞摘要，未核對 | https://www.storm.mg/article/1652917 |
| 2 端點 | `term.ptt.cc`（網頁）、`wss://ws.ptt.cc/bbs`（PCMan、Welly） | 社群說明頁，無日期 | https://hackmd.io/@twbbs/PTTSecure（2026-11-06 讀取） |
| 2 同帳號連線數 | 「3 個」，第三方 PiTT README；重複登入時客戶端提示「刪除」 | 社群 | https://github.com/kimieno/android.pitt（搜尋摘要） |
| 2 閒置斷線、伺服器踢除 | 查不到 | 無資料 | — |
| 2 其他 | 缺 Origin 會 403；預設 Big5 | 社群 | https://ithelp.ithome.com.tw/articles/10266190（搜尋摘要） |
| 3 版本 | 2.3.16（2026-11-06）、2.3.10（2026-10-09）、1.2.19（2025-07-10） | 官方（PyPI） | https://pypi.org/project/PyPtt/#history |
| 3 授權、Python | LGPLv3；`Requires-Python >=3.11`；classifier 含 3.12 | 官方（PyPI） | https://pypi.org/pypi/PyPtt/json |
| 3 替代套件 | pyte 0.8.2（2023-11-12）、LGPLv3（classifier）、`requires_python >=3.8` | 官方（PyPI） | https://pypi.org/pypi/pyte/json |
| 4 新帳號讀 Gossiping 等 | 查不到；摘要：2018 停註冊後重開，需手機門號驗證（社群指南） | 無資料 | https://uptogo.com.tw/科技/ptt-辦新帳號？/ |
| 5 AID 轉換 | 字元表 `0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_`；十進位取 6 位、`.A.XXX` 取 2 位；`.html` 補 `00`（未實測） | 社群 gist | https://gist.github.com/PttCodingMan/d128f64ad5e79f7ddb840c020bafa2ec |
| 6 推文時間、刪文、編輯 | 查不到 BBS 格式與刪文、編輯後樣子 | 無資料 | — |

**PyPtt 原始碼**（commit `cfb2bd9e5d94e1ff1743c7f37171513630c6380a`，2026-11-06T01:25:44Z；來源 https://api.github.com/repos/PyPtt/PyPtt/commits?per_page=1 ，檔案在 `https://raw.githubusercontent.com/PyPtt/PyPtt/<commit>/PyPtt/…`）
行號由讀取模型計數，未在本地逐行核對，使用前請對照。

| 問題 | 結論（檔案:行號） |
|---|---|
| 1 整篇翻頁、按鍵數 | 否。`get_post` 只讀一篇：一次明確 `send`（`_api_get_post.py:131`），正文另由 `get_content` 讀（:193）。`get_content` 送 Enter、→、↓ 直到文末（`_api_util.py:60,92-95,217-237`）；總按鍵數依文長，未計算 |
| 2 速率控制 | 查不到內建速率限制或固定延遲。`_api_bucket.py` 無節流；唯一 `time.sleep(1)` 在連線失敗重試（`connect_core.py:205`，最多 2 次）；`screen_timeout` 預設 3.0 秒（`PTT.py:119`） |
| 3 關 log、密碼 | 預設 `log_level=INFO`（`PTT.py:90`）；`SILENT`（NOTSET）即關閉（`log.py:19,90-91`）。登入時寫帳號 ID（`_api_loginout.py:80`）；密碼未進 log 呼叫；送出時 secret 遮蔽（`connect_core.py:346-349`） |
| 4 能否用 AID | 能。`get_post(api, board, aid=None, index=None, …)`（`_api_get_post.py:22-25`），aid 與 index 二選一（:53-61），`check_aid`（:105-116）。AID↔檔名轉換不在此檔，查不到 |
| 其他 | 自動回答「您想刪除其他重複登入的連線嗎」，依 `kick_other_session`，預設值查不到（`_api_loginout.py:59,61-62,96`）；提交訊息稱 PTT1 `/bbs/` 回 404 已改 `/bbs`（#235，維護者說法，非 PTT 公告） |

**對 7.31 三個待決定的影響**
1. 實驗用套件：PyPtt 維護中、授權與 Python 可接受；原始碼顯示 aid 讀文與 SILENT 可用，但速率要由程式自己節流（7.31 B 的 20 秒與 1 次／秒要自寫）；整篇讀取按鍵數未計，需實測。
2. 同時登入數：只有第三方「3 個」說法，依 7.31 C 門檻 2 視為未證實，需甲方決定是否實測。
3. 站規若禁止程式登入：外部查不到明文，無法判定；PyPtt FAQ 說 PTT 有防機器人機制。需甲方直接查站規原文。

**建議（非決定）**：要不要實測同時登入數、站規原文由甲方在瀏覽器取得（agent 不連 PTT）。
