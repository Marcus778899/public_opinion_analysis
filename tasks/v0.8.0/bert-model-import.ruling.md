TEST_WRONG fbdab12

# 仲裁：bert-model-import 驗收測試

- 觸發：worker disputes（`reports/bert-model-import.json`），非 qa FAIL
- 測試目錄歷史：`tests/unit/acceptance/bert-model-import/` 只有 qa 的 `42f8b4e test(bert-model-import)` 一個 commit，沒有被他人改動
- 依據：開發規格 7.27「威脅與對策」本機檔案系統列（`model_version` 限 `^[a-z0-9][a-z0-9-]{0,63}$`）、「測試」（helper 由 bert-skeleton 完成，各單只呼叫、不修改）；派工單驗收條件第 2 條
- 重現：`package_members(..., model_version='')` 產出的 card `model_version` 為 `bert-test-202610210000`（helper 寫 `model_version or model_version_for(quantized)`）；`uv run pytest tests/unit/acceptance/bert-model-import` → 1 failed, 25 passed，只有 `[]` 案例失敗

## 逐條判定

| 測試名稱 | 契約條文 | 判定與理由 |
|---|---|---|
| `test_invalid_model_version_is_rejected[]`（`version=""`） | 7.27 本機檔案系統：`model_version` 須符正規式 | **測試錯**。條文本身要求拒絕空字串，但測試經 helper 打出的 zip 實際上是 `model_version=bert-test-202610210000` 的合法模型包，依契約應被接受；測試要求拒絕與契約矛盾。實作照契約接受它是對的 |
| `test_invalid_model_version_is_rejected` 其餘 8 個案例 | 同上 | 測試正確（非空字串原樣寫進 card），且已通過 |
| 其他驗收測試（雜湊、白名單、路徑穿越、大小上限、目標已存在、card 非 JSON、64 字元版本） | 7.27 模型包格式、威脅與對策 | 測試正確，已通過；不在本次爭議範圍 |

## 測試應該怎麼改（qa；不可改 helper）

`_members_with_version` 不要靠 helper 的 `model_version` 參數寫入非法值，改成先用預設值產生，再改寫 card JSON（同檔 `test_card_hash_pointing_to_other_content_is_rejected` 的作法）：

```python
def _members_with_version(tmp_path: Path, version: str) -> dict[str, bytes]:
    members = package_members(tmp_path / "work")
    card = json.loads(members[CARD_FILE])
    card["model_version"] = version
    members[CARD_FILE] = json.dumps(card).encode()
    return members
```

- 這樣 `""` 案例真的帶空字串版本，其餘案例與 `test_model_version_of_64_chars_is_accepted` 行為不變
- 改完 `[]` 案例預期拒絕（`ModelPackageError`），worker 實作的 `MODEL_VERSION_RE.fullmatch` 已會拒絕空字串，不需改實作

## 契約問題

- helper `package_members` 把空字串視同未指定（`or` 而非 `is None`），是 helper 的行為陷阱，不是契約矛盾；helper 依 7.27 不可由各單修改。若要改成 `is None`，另開修正單給 helper 的負責人（非決策分級四類，不需 D-編號）
