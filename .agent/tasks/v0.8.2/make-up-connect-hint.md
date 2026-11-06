# 派工單 make-up-connect-hint

- **類型**：chore
- **負責**：backend
- **通道**：fast
- **目標**：`make up` 的說明寫清楚：只起基礎設施、沒有 init 時 connect 會 unhealthy、`--wait` 會失敗，以及要完整啟動該用哪個指令（#309，UAT v0.8.2 F-2）
- **背景**：
  - 開發規格 7.30 B「已知限制」：connect 健康檢查要求 `radar-cdc` 存在；沒有 `--profile app` 的 `init` 就不會建立 connector，start_period 過後 unhealthy，`up --wait` 回非 0
  - `Makefile` 的 `up` 目前只寫「啟動基礎設施」，直接用 `make up` 的人會以為環境壞了
  - 甲方決定這版一起處理；範圍只有補說明，不改 `up` 的行為、等待條件或健康檢查
- **設計依據**：`docs/development-spec.md` 7.30 B；`docs/uat/v0.8.2.md` F-2；#309
- **相依**：無
- **負責檔案**：
  - `Makefile`
  - `tests/unit/test_makefile_up_hint.py`
- **禁區**：不改 compose、健康檢查、`up` 的實際指令；不改其他 target；不改文件（與 7.30 不符時回報 manager）
- **驗收測試**：無
- **驗收條件**：
  - [ ] Makefile 既有的說明機制看得到 `up` 的這項限制與要改用的指令
  - [ ] `up` 實際執行的指令不變
  - [ ] 新增單元測試檢查 `up` 的說明含這項提示，防止之後被改掉
  - [ ] `make check` 通過
- **驗證指令**：`make check`；`uv run pytest tests/unit/test_makefile_up_hint.py -v`
- **回報檔**：`.agent/reports/make-up-connect-hint.json`

## 執行資訊（ae task 產生）

- Issue：#312
- 分支：`chore/make-up-connect-hint`（從 develop 開出）
- 工作目錄：`.worktrees/make-up-connect-hint`；所有修改、指令、commit 都在這裡做，回報檔寫在主目錄 `.agent/reports/`
