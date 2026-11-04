# 派工單 bert-skeleton

- **類型**：chore
- **負責**：architect
- **目標**：階段 8 的骨架：相依套件、設定、topic、migration、各模組骨架與驗收測試共用 fixture，以及完整實作的測試用小 ONNX 模型 helper
- **背景**：設計已核可（PR #154）。D-020 執行期 onnxruntime＋tokenizers（開發用 onnx）；D-021 改為 ckiplab 與 hfl macbert 各訓一版（7.27 派工順序第 8 步原寫「fp32 與 int8 兩個模型包」，要同步成兩個預訓練模型 × fp32／int8，notebook 以參數選預訓練模型）；D-023 shadow 上限 2 CPU、1.5g、`INFERENCE_THREADS=2`。另外 D-018：開發規格第 38 行忽略檔說明補一句「`tasks/` 由 `.gitleaks.toml` 整體排除（D-018）」
- **設計依據**：`docs/development-spec.md` 7.27（檔案分工、測試、派工順序）；`docs/realtime-sentiment-radar-design.md` 11.1；D-020～D-024、D-018
- **相依**：無
- **負責檔案**：
  - `pyproject.toml`
  - `uv.lock`
  - `Makefile`
  - `.env.example`
  - `infra/docker-compose.yaml`
  - `infra/kafka/topics.yaml`
  - `infra/clickhouse/migrations/0006_predictions_shadow.sql`
  - `src/radar/common/kafka/names.py`
  - `src/radar/common/settings.py`
  - `src/radar/ml/`
  - `notebooks/`
  - `tests/helpers/onnx_model.py`
  - `tests/unit/helpers/test_onnx_model_helper.py`
  - `tests/unit/acceptance/`
  - `tests/integration/acceptance/`
  - `tests/unit/ml/`
  - `tests/unit/common/`
  - `docs/development-spec.md`
  - `docs/realtime-sentiment-radar-design.md`
- **禁區**：骨架以外的實作留給各單（用 `TODO(<該單 task_id>)` 標記，例 `TODO(bert-classifier)`），helper 例外要完整實作；驗收測試目錄只建上層共用 fixture，不建各單的子目錄；不改現行推論行為與 `predictions` 的寫入；不改 `scripts/`、`.claude/`、`contracts/`、`CLAUDE.md`
- **驗收測試**：無
- **驗收條件**：
  - [ ] `make check` 通過；helper 單元測試涵蓋 tokenizer、fp32／int8 小模型、模型包 zip 雜湊
  - [ ] `docker compose -f infra/docker-compose.yaml --env-file .env build inference` 在本機（arm64）成功，容器內 `import onnxruntime, tokenizers` 成功（附輸出；用 `docker compose ... run --rm` 執行）
  - [ ] 開發規格 7.27 同步 D-021（兩個預訓練模型 × fp32／int8、notebook 參數）與 D-023，第 38 行補 D-018 說明
  - [ ] 現行推論的單元與整合測試不受影響（跑前 `docker compose ls` 確認沒有其他測試堆疊，做完 `down -v`）；PR 的 CI 全綠
- **驗證指令**：`make check`；上面的 compose 指令
- **回報檔**：`reports/bert-skeleton.json`

## 執行資訊（task.py 產生）

- Issue：#155
- 分支：`chore/bert-skeleton`（從 develop 開出）
- 工作目錄：`.worktrees/bert-skeleton`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `reports/`

## 追加 2026-10-21

### 負責檔案更新（manager，取代原欄位：補 e2e compose 的 shadow log volume）

- **負責檔案**：
  - `pyproject.toml`
  - `uv.lock`
  - `Makefile`
  - `.env.example`
  - `infra/docker-compose.yaml`
  - `infra/docker-compose.e2e.yaml`
  - `infra/kafka/topics.yaml`
  - `infra/clickhouse/migrations/0006_predictions_shadow.sql`
  - `src/radar/common/kafka/names.py`
  - `src/radar/common/settings.py`
  - `src/radar/ml/`
  - `notebooks/`
  - `tests/helpers/onnx_model.py`
  - `tests/unit/helpers/test_onnx_model_helper.py`
  - `tests/unit/acceptance/`
  - `tests/integration/acceptance/`
  - `tests/unit/ml/`
  - `tests/unit/common/`
  - `docs/development-spec.md`
  - `docs/realtime-sentiment-radar-design.md`

## 追加 2026-10-21

### reports/bert-skeleton.review.md

REQUEST_CHANGES 573b966

# bert-skeleton review 第二輪（PR #156，573b966）

上一輪的 4 條都已處理（見下表）。researcher 後來補了調查末節「safetensors 與 ckiplab tokenizer」，7.27 還停在「待調查」的寫法，所以 tokenizer 的規定要跟著調整（第 1 條）。另外，7.27 的 D-025 段和 `docs/decisions.md` 寫的不一樣（第 3 條）。這輪只要改 `docs/development-spec.md` 7.27，程式、notebook、compose 都不用動。

## 上一輪 4 條

| 條 | 位置 | 結果 |
|---|---|---|
| 1 safetensors 對策 | :1311 | 已處理。改為「做不到」並引用調查「模型 revision」節，載入方式寫待決定 D-025，也保留了 revision、`trust_remote_code=False`、card。漏了 Google tokenizer 的 repo，見第 1 條 |
| 2 tokenizer 規定 | :1265、:1367 | 驗證的部分（`Tokenizer.from_file` 重新編碼後 ids 要一致，logits 比對共用這組 ids）已處理。產生來源要依調查結果改，見第 1 條 |
| 3 需調查改寫 | :1386–1390 | revision 已改為引用調查，沒有重抄 hash，也寫了甲方要用 HF API 核對，這部分已處理。需調查 1、2 已經查到答案，見第 2 條 |
| 4 `bert-notebook` 相依 | :1337 | 已處理。等 1 與 D-025，3～6 不受影響 |

## 必改

1. `docs/development-spec.md:1265`（「匯出」的 tokenizer）、`:1367`（自行決定表）、`:1311`（威脅表「預訓練模型的來源」）：tokenizer 依調查結果改成照 ckiplab README 的做法。
   - 依據（調查末節 2、3、4）：ckiplab README 要求改用 `BertTokenizerFast.from_pretrained('bert-base-chinese')`，也就是 Google 版。兩邊的 `vocab.txt` 是同一個 git blob（`ca4f978…`），內容完全一樣。
   - 為什麼還是要改：`vocab.txt` 只有詞表。斷詞的行為設定（例：`do_lower_case`）寫在 `tokenizer_config.json`，而調查沒列出 ckiplab 有這個檔。只從 ckiplab 的 `vocab.txt` 載入，會吃到 `BertTokenizerFast` 的預設值，可能和預訓練時用的 Google tokenizer 不一樣。PTT 文章常夾英文，大小寫的處理一不同，ids 就不同。現有的 ids 一致性檢查只比對推論端和訓練端，兩邊都用了錯的 tokenizer 時抓不到。
   - 要改成：
     - `macbert` 用自己 repo 在釘選 revision 下的 tokenizer。
     - `ckip` 用 `google-bert/bert-base-chinese` 的 tokenizer，同樣釘 revision。值在調查末節第 4 項，7.27 只寫引用。
     - 兩者都以 `BertTokenizerFast` 載入後 `save_pretrained`。後面的 ids 一致性檢查維持原樣。
     - 刪掉「從 `vocab.txt` 轉換；是否改用 Google 版 tokenizer 見需調查 2」。
   - `:1367` 自行決定表的那一列同步改寫，理由寫「ckiplab README 指定；詞表相同但行為設定不在 vocab.txt」。
   - `:1311` 的「釘 `revision`」補上「含 ckip 用的 Google tokenizer repo」，`base_model` 記進 card 時也要一併記 tokenizer 的來源與 revision。
   - 這屬於技術細節，不在決策分級四類內，由 architect 決定，不用開 D-編號。notebook 第一格的 `BASE_MODELS` 要多一個 tokenizer 來源的欄位，這是 `bert-notebook` 的實作，本單不用改 notebook。
2. `docs/development-spec.md:1386–1390`（需調查）：需調查 1、2 都已經有結果，不要再寫成問句。改成引用結果，一行一項，不重抄 hash：
   - 1：macbert 沒有轉換 PR。ckiplab 有 SFconvertbot 開的 `refs/pr/1`，還沒合併。這是 D-025 選項 B 的依據。
   - 2：已依調查定案，做法見第 1 條。
   - revision 那一項要補上 Google tokenizer 的 revision（調查末節第 4 項），甲方第一次執行時用 HF API 核對。
   - 段落標題改成「已調查」或類似的名稱，不要再列成待辦。
3. `docs/development-spec.md:1382`（待決定段）：這段把 D-025 的選項重寫了一次，內容和 `docs/decisions.md` 對不上。7.27 的 B 寫「revision 改釘 HF 的 safetensors 轉換 PR commit」，沒有分模型；decisions.md 的 B 是「ckiplab 改釘轉換 PR，macbert 照 A」，而且調查已經確認 macbert 沒有轉換 PR。同一件事只寫一次：
   - 這段縮成一行：「pickle 權重的載入方式：待決定 D-025（選項與建議見 `docs/decisions.md`）；本機與 VM 只載 ONNX／JSON，不受影響」。
   - A／B／C 的內容與建議只留在 decisions.md。

## 已檢查（通過）

| 項目 | 結果 |
|---|---|
| 變更範圍 | 573b966 只改 `docs/development-spec.md`，有 12 行新增、3 行刪除，都在 7.27 內。程式、compose、migration、helper 都沒動 |
| hash 不重抄 | 7.27 沒有 40 碼 hash，值都引用調查（qa 證據也有確認） |
| D-025 與 BOARD | D-025 在 decisions.md 的「待決定」，還沒定案。7.27 沒有自己定暫定值；寫了「決定前 notebook 不寫載入權重的檢查」，qa 不會照這段寫出必然失敗的測試 |
| 驗證 | qa：`make check` 1214 passed；CI 的 Check、Integration Test、Security 三項都通過 |
| 上一輪的其他項目 | 程式沒變，沿用 c95cff5 那輪的結果 |
