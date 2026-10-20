---
name: backend-standards
description: 後端實作與設計規範（不限語言：Java、Python、Go、Node…）。實作或設計 API、資料存取、DB migration、認證授權、錯誤處理、設定、log、背景工作，或交付後端任務前對照檢查清單時使用。
---

# 後端規範

只講概念；各語言的工具對照（測試、覆蓋率、lint、migration、相依稽核）在 `references/<語言>.md`，用到哪個語言才讀。
專案的契約、設計、決策優先於這裡；矛盾就照契約做並回報，不要自己改契約。

## 1. 介面（以契約為準）

- 請求與回應的欄位、型別、狀態碼、錯誤格式都照 `docs/contracts/`；契約沒寫的欄位不要自己加，缺就回報
- 錯誤回應全專案同一種格式（例：`{"error": {"code": "TODO_TITLE_EMPTY", "message": "..."}}`）；`code` 是給程式判斷的穩定字串，`message` 給人看，不帶堆疊、SQL、內部路徑
- 狀態碼語意固定：400 輸入格式錯、401 沒登入、403 沒權限、404 不存在、409 衝突（重複、版本不符）、422 商業規則不允許、5xx 只用在伺服器自己的錯
- 列表一律分頁（limit 有上限）；排序欄位白名單
- 會被重試的寫入（付款、建立訂單、外部 webhook）要冪等：idempotency key 或唯一約束

## 2. 輸入與信任邊界

- 所有外部輸入（body、query、header、path、檔案、webhook、第三方 API 回應）在邊界驗證一次：型別、長度、範圍、格式、列舉值；內部函式信任已驗證的型別
- 驗證失敗回 400／422，不要靜默修正（例外：契約明寫要 trim）
- SQL 一律參數化或用 ORM 的參數綁定；不可字串拼接查詢、命令、路徑
- 檔案路徑、URL（SSRF）、重新導向目標用白名單，不可直接用使用者輸入

## 3. 認證與授權

- 每個端點明確宣告需不需要登入；預設需要（fail closed），公開端點要在契約寫明
- 授權檢查在伺服器端、針對「這筆資料」：不只檢查已登入，還要檢查擁有者或角色（防 IDOR：改網址的 id 就看到別人的資料）
- 密碼用專用演算法雜湊（argon2、bcrypt、scrypt）；token、session 用安全亂數；比對 secret 用常數時間比較
- 不在 URL、log、錯誤訊息出現 token、密碼、個資

## 4. 資料與 migration

- schema 只透過 migration 改，migration 進版控、可重複執行結果一致；不手動改資料庫
- 變更要能和舊版程式並存（expand → 遷移資料 → contract）：先加欄位／表，程式改用新欄位，下一版才刪舊的；不在同一版改名或刪除仍被讀取的欄位
- 每個 migration 要有 down（或寫明不可逆的理由，不可逆屬於決策分級第 ④ 類，要先問甲方）
- 一個業務動作的多筆寫入包在同一個 transaction；transaction 裡不呼叫外部服務
- 查詢注意 N+1；常用的過濾、排序、外鍵欄位要有索引

## 5. 設定、log、可靠性

- 設定只從環境變數讀（名稱寫在 `.env.example`）；程式裡沒有預設的 secret、預設帳密、寫死的 port 與網址
- 啟動時驗證必要設定，缺了就啟動失敗（fail fast），不要用不安全的預設值頂著
- 結構化 log（JSON 或 key=value），帶 request id；等級分清楚；不記 secret 與個資
- 呼叫外部服務一定設 timeout；重試只用在冪等操作，要有上限與退避
- 錯誤不吞掉：要嘛處理，要嘛往上丟；最外層統一轉成錯誤格式並記 log

## 6. 測試（配合流程）

- 驗收測試（`驗收測試` 目錄）是 qa 寫的考題，不可改；自己的單元測試放別的目錄
- 新增或修改的商業邏輯都要有單元測試（成功、失敗、邊界各至少一個）；CI 會檢查這次改到的程式碼至少 80% 被測試執行到（`scripts/coverage_gate.py`），沒過 PR 就不能合併
- 碰到資料庫的程式用真的資料庫跑整合測試，不要只 mock repository；DB 與整合測試都在 docker compose 裡跑（見下一節）
- 測試只連自己的 DB：不可連 `.env` 指向的共用開發 DB（平行的 worktree 會互撞，主目錄跑舊 schema 時也會壞）

### 整合測試與 docker compose

本機的 Bash 在 sandbox 裡，docker 不能直接用；設定讓 `docker compose …` 這個指令在 sandbox 外跑（甲方允許的例外）。所以：

- 需要 DB 等服務的測試，放在 compose 的 `test` 服務裡跑：`docker compose --env-file .env -f .worktrees/<id>/compose.yaml run --rm test`（在主目錄下指令）
- 設定從主目錄的 `.env` 讀：worktree 裡沒有 `.env`（sandbox 擋住所有 `.env`，不連進 worktree），所以一定要 `--env-file .env`；compose 檔用 `${KEY:?說明}` 取值、不用 `env_file: .env`，忘了 `--env-file` 會直接失敗，而不是默默帶空值跑
- 直接下 `docker compose` 指令：包在 `make`、script 裡，或跟 `cd`、`&&`、重導向寫在同一個指令裡，都會留在 sandbox 而失敗
- 用 `-f .worktrees/<id>/compose.yaml`：專案名稱跟著 worktree 目錄，每張單有自己的 DB 容器，平行開發不互撞；測試用的 DB 不要對外開 port
- `make check` 只放不需要容器的檢查（lint、單元測試）；需要容器的整合測試另外一個指令，寫進派工單的驗證指令。CI 兩個都跑
- compose 檔、Dockerfile 是受保護路徑（fast 通道自動升級、要 architect review）：它們在 sandbox 外執行，能碰到整台電腦，不要加入跟測試無關的 volume 掛載
- Linux／WSL2：容器預設用 root 跑，掛載進去的 worktree 會留下 root 擁有的檔案（快取、報告），之後刪 worktree 會失敗。`test` 服務設 `user: "${HOST_UID:-1000}:${HOST_GID:-1000}"`（bash 的 `UID` 沒有 export，用預設值或在 `.env.example` 加這兩個變數）；macOS 的 Docker Desktop 會自動對應，不受影響
- CI 沒有 sandbox：只用 compose 開 DB 等服務（`docker compose up -d db`），測試與 `make coverage` 直接在 runner 上跑。在容器裡跑的話，報告裡是容器內的路徑，對不回 repo

### 覆蓋率報告（`make coverage`）

- 只在 CI 用：跑全部測試（含整合測試，需要的服務由 CI 先開好），把報告寫到 `coverage-reports/*.xml`：一律 XML（Cobertura 或 JaCoCo），不可用 LCOV（diff-cover 不能混用）
- 每一端都要產報告（前後端都有就各一份）：改到的程式檔不在任何報告裡，CI 直接失敗
- 沒被任何測試載入的檔案也要出現在報告裡（各語言的設定見 references），否則新檔案不寫測試也量不到
- 本來就不量的程式檔：設定檔、migration、產生的程式已預設排除（`coverage_gate.py` 的 `EXEMPT`）；專案自己的（例：進入點 `cmd/server/main.go`）寫進 `.coverage-exempt`，一行一個樣式。它是受保護路徑，加一條要 architect review
- 報告的路徑要能對回 repo 根目錄；本機可以用 `diff-cover coverage-reports/*.xml --compare-branch develop` 確認有數字
- 測試不依賴執行順序、時間、外部網路；時間與亂數用可注入的來源

## 交付前檢查清單（寫回報前逐條對照，沒做到的寫進 open_questions）

- [ ] 回應格式、狀態碼、錯誤 code 與契約一致；沒有契約外的欄位
- [ ] 所有外部輸入在邊界驗證；沒有字串拼接的 SQL、命令、路徑
- [ ] 每個新端點都有授權檢查（含「是不是這筆資料的擁有者」）
- [ ] 沒有寫死的 secret、帳密、port、網址；新設定已加進 `.env.example`
- [ ] migration 可和舊版程式並存、有 down；多筆寫入在同一個 transaction
- [ ] 外部呼叫有 timeout；log 沒有 secret 與個資
- [ ] 新邏輯有單元測試；驗證指令（`make check`、需要時加整合測試的 `docker compose … run --rm test`）實際跑過且全過
