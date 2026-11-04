APPROVE 243b510

# Review PR #217 shadow-missing-model-exit（第 3 輪）

本輪只檢查上一輪 APPROVE（f10dc5d）之後的變更：依仲裁（reports/shadow-missing-model-exit.ruling.md，TEST_WRONG d51ba3c）補整合驗收 fixture 的一行。

## 檢查項目

| 項目 | 結果 |
|---|---|
| f10dc5d 之後的 commit | `d51ba3c` merge develop、`243b510` test 修正，共 2 個 |
| `d51ba3c` merge | `git show --remerge-diff` 沒有輸出：合併沒有衝突、沒有手動改動；帶進來的 10 個檔都是 develop 上 #216 的變更，不在 PR diff 裡 |
| `243b510` 內容 | 只改 `tests/integration/acceptance/bert-shadow-inference/test_shadow_service.py` 1 行（+1/-0），在 `env` fixture 的 `card = make_card(e.model_version)` 後面加 `(tmp_path / "model_card.json").write_text(card.model_dump_json(), encoding="utf-8")`；和仲裁「要怎麼改」逐字一致，沒有改測試函式、assert，也沒有改 `load_classifier` 的 fake |
| 其他 PR 檔案 | `src/radar/ml/inference/`、`infra/`、`docs/development-spec.md`、`tests/unit/ml/inference/`、`tests/unit/acceptance/shadow-missing-model-exit/` 在 f10dc5d→243b510 之間 diff 是空的，上一輪的審查結論不變 |
| 負責範圍 | 改的檔案已在派工單「追加 2026-10-29」加入負責檔案與驗收測試清單；PR 對 develop 的 diff 共 6 個檔，都在負責範圍內 |
| CI run 40811594103 | headSha 243b510；Check、Integration Test、Security 三個 job 都 success。Integration Test 1883 passed，含原本失敗的 8 個 shadow 測試（例 `test_shadow_role_writes_only_shadow_topic`、`test_shadow_undecodable_message_lands_in_dlq_and_later_events_still_processed`）；diff-cover 步驟通過；Check 1522 passed |
| TODO | `grep -rn "TODO(shadow-missing-model-exit)" src tests` 沒有結果 |
| 可合併 | `gh pr view 217`：MERGEABLE，三個 status check 都是 SUCCESS |

## 問題

無。
