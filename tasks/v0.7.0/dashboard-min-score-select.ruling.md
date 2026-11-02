TEST_OK 2698314

# 仲裁：dashboard-min-score-select 驗收測試（鎖定 c15d493，worktree HEAD 2698314）

結論：鎖定的驗收測試照契約寫、與甲方方向一致，**問題不在測試**。第 2 次 FAIL（qa 0848c15）的原因是開發規格 7.25 的文件沒同步，不是測試錯。
判定依據（本功能沒有 `docs/contracts/`，以這三份為準）：派工單驗收條件、開發規格 7.25（面板說明段＋威脅表）、manager 轉述的甲方方向（一律 percentencode、由 ClickHouse 解碼；只做靜態檢查加正常值檢查，不用攻擊字串）。

## 檢查了什麼

| 項目 | 結果 |
|---|---|
| c15d493 之後測試有沒有被改 | `git diff c15d493 HEAD --stat -- tests` 無輸出（之後只動 `radar.json`、`development-spec.md`） |
| 測試讀的是不是真的 dashboard | `load_dashboard()` 走 `/api/dashboards/uid/radar`（provisioning 讀回），`run_panel` 走真的 plugin 的 `/api/ds/query` |
| 展開模擬與 Grafana 13.0.2 是否一致 | qa 0848c15 證據：bundle 的 percentencode 原始碼抽出來用 node 跑，與 `_dash._percentencode`／`urllib.parse.quote(..., safe="")` 逐筆相同；All、空選取的展開也相同 |
| 靜態檢查對 HEAD 的結果（我自己跑的） | 在 worktree 用 `references()` 掃全部面板 rawSql：16 個引用，`{('board','percentencode',True), ('min_score','percentencode',True)}`，全都在 SQL 單引號內 |
| 2698314 的文件 | qa 指出的「威脅表：，」與「`'a','b'`」已經移除；1035 行改寫成「`allowCustomValue: false` 只是 UI 層限制…不是安全防線」，跟 qa 建議的寫法一致（文件內容是 qa 下一輪要驗的，這裡不判） |

## 逐條判定

| 測試名稱 | 契約條文 | 判定與理由 |
|---|---|---|
| `acceptance/.../test_min_score_variable_is_dropdown_with_four_options_defaulting_to_half` | 派工單條件 1；7.25「`min_score` 下拉選單 0.4／0.5／0.6／0.7、預設 0.5，說明文字」 | 正確。檢查了 type=custom、選項的順序與值、current=0.5、query、不能多選也沒有 All、description 不是空的。說明文字的措辭屬於 UI 文案，測試只要求「有寫」是對的 |
| `acceptance/.../test_every_board_and_min_score_reference_uses_percentencode`、`dashboard/test_variable_formats.py` 同名測試 | 條件 2（依甲方方向改用靜態驗證）；7.25「SQL 一律寫 `${board:percentencode}`、`${min_score:percentencode}`」、威脅表「靜態測試要求每個引用都是此格式」 | 正確。`ALLOWED_FORMATS = {"percentencode"}`，`$board`、`${board}`、`[[board]]`、`:sqlstring`、`:singlequote`、`:csv` 和沒寫格式的引用都會被抓到；`references()` 會略過 SQL 註解，引號內外都會掃到 |
| `acceptance/.../test_min_score_options_and_default_are_fixed_numbers`、`test_min_score_options_are_all_fixed_numbers` | 7.25 下拉選項；甲方方向「只帶固定數字」 | 正確 |
| `test_every_min_score_option_gives_the_seeded_distribution`、`test_min_score_option_moves_post_between_category_and_unsure` | 7.25 面板 2、6「`score < min_score` 為不確定」；條件 1 的四個選項 | 正確。四個門檻在 0.55／0.65 兩邊都有測到，涵蓋邊界 |
| `test_chinese_board_name_with_underscore_is_matched_exactly`、`test_chinese_board_name_with_underscore_returns_its_own_rows_only`、`test_two_selected_boards_with_chinese_names_both_appear`、`test_board_panels_reference_board_variable` | 7.25「`has(splitByChar(...decodeURLComponent(...)))` 精確比對」；正常值檢查 | 正確。中文、底線、相近名稱、多選、沒有資料的看板都有涵蓋；名稱含 `%XX` 也間接保證 board 引用一定要在引號內、一定要解碼，否則語法錯或比對不到 |
| 刪掉的攻擊字串測試（`test_board_value_with_quote_...`、`test_min_score_with_quote_...` 等） | 甲方方向「驗收不用攻擊字串」 | 刪除合理，與方向一致；上一輪 qa 指出的「報錯就放行」的缺陷也跟著消失 |

## 補強建議（不擋這張單，可另開 qa 單）

| 檔案:位置 | 缺口 | 建議 |
|---|---|---|
| `tests/integration/dashboard/_dash.py` `Ref.in_string`；兩個 `test_every_board_and_min_score_reference_uses_percentencode` | 7.25 寫「放在 SQL 單引號裡」，但靜態測試只檢查格式，沒用 `in_string`。如果 `min_score` 沒加引號直接比較（例 `s.score < ${min_score:percentencode}`），正常值測試照樣會過，但網址可以帶 `s.score` 這類識別字、或帶 `%` 運算子，改變運算式。現在的 HEAD 16 個引用全都在引號內，所以沒有實際問題 | 斷言再加上 `r.in_string`；威脅表「靜態測試要求…」一併寫成「此格式且在單引號內」 |
| `tests/integration/dashboard/test_variable_formats.py:3` docstring | 「引用不在 SQL 引號內」是 sqlstring 時代的說法，跟現在的規定剛好相反 | 改成「引用在 SQL 單引號內、格式只用 percentencode」 |
| `test_variable_formats.py` `test_chinese_board_name_with_underscore_returns_its_own_rows_only` 的 `P_VOLUME` 參數 | 時序寬表的看板名稱在欄位 labels，不在 values（上一輪 qa 問題 3-2），`other.board not in text` 對這個面板等於沒檢查；現在比對是 `has()` 精確比對，其他 4 個面板有實際檢查到 | 對 `P_VOLUME` 改成比對 frame 的欄位 labels，或用欄位數判斷 |

## 契約問題

| # | 問題 | 分級 |
|---|---|---|
| 1 | 派工單驗收條件 2 還寫「經網址參數帶入含單引號或 SQL 片段…不可執行注入的 SQL」（動態驗證），跟甲方後來定的「只做靜態加正常值」方向不一致；`docs/decisions.md` 查不到這個方向的紀錄 | 不必開新的 D-編號（甲方已經表態）；請 manager 把條件 2 改成照甲方方向的寫法，並把甲方的方向記錄下來，讓 qa、security 有地方可以引用 |
