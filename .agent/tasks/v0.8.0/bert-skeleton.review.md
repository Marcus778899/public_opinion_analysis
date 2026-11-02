APPROVE 407d342

# bert-skeleton review 第三輪（PR #156，407d342）

第二輪追加的 3 條都已處理。407d342 只改 `docs/development-spec.md` 7.27（8 行新增、8 行刪除），程式、compose、migration、notebook 都沒動。引用的 D-025 與調查末節以主目錄（develop）的版本核對，內容都對得上。

## 第二輪必改 3 條

| 條 | 位置 | 結果 |
|---|---|---|
| 1 tokenizer 改照 ckiplab README | :1265、:1311、:1367 | 已處理。`macbert` 用自己 repo 的 tokenizer，`ckip` 用 `google-bert/bert-base-chinese` 的 tokenizer，兩者都釘 revision，值引用調查末節第 4 項（對過 develop 版本，第 4 項就是 Google repo 的 main commit）。兩者都用 `BertTokenizerFast` 載入後 `save_pretrained`，ids 一致性檢查保留。舊句「從 `vocab.txt` 轉換」已刪。威脅表補了「含 `ckip` 用的 Google tokenizer repo」，card 也會記 tokenizer 的來源與 revision。自行決定表的理由照要求寫了 |
| 2 需調查改為引用 | :1386–1391 | 已處理。標題改成「已調查」，每項一行。revision 項含 Google tokenizer，也保留了甲方用 HF API 核對。轉換 PR 項引用末節第 1 項（develop 上的內容是：macbert 沒有，ckiplab 有 `refs/pr/1` 但未合併），並寫明這是 D-025 選項 B 的依據。tokenizer 項寫已定案，指向「匯出」。7.27 沒有 40 碼 hash |
| 3 D-025 只引用 | :1382 | 已處理。縮成一行，A／B／C 的選項與建議只留在 `docs/decisions.md`（develop 版 D-025 第 8–12 行），兩邊不再有內容對不上的地方 |

## 已檢查（通過）

| 項目 | 結果 |
|---|---|
| 變更範圍 | 只動 7.27 的 5 處，沒有改到負責檔案以外的東西 |
| 分支尚未含 develop 的 faae283 | 分支上還沒有調查末節與 D-025，所以合併前的分支內引用暫時指不到內容。合併後就成立，不擋合併 |
| 驗證 | qa PASS 407d342：`make check` 1214 passed；CI 的 Check、Integration Test、Security 三項都通過；`grep -rn "TODO(bert-skeleton)" src tests` 沒有結果 |
| 前幾輪的其他項目 | 程式沒變，沿用 c95cff5 那輪的結果 |

## 不擋合併的建議

- `docs/research/bert-stage8.md` 末節第 5 項寫「與上方建議衝突，由 architect 決定」。architect 已在 7.27 定案（Google 版 tokenizer）。之後可以請 researcher 在第 5 項註明「已定案，見開發規格 7.27」，避免讀者以為還沒決定。這個檔不在本單範圍內。
