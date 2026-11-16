APPROVE 9f22e9f

# Review bbs-spike-report（PR #326，第 3 輪）

## 檢查了什麼

- `git diff da79045 9f22e9f`（上一輪 review 之後的修正，2 檔、4 行），另外重讀報告第 1 節全文與開發規格 7.31 結論
- 負責檔案：只動了 `docs/reports/bbs-spike.md`（115 行，≤ 150）與 `docs/development-spec.md`（只有 7.31 結論 1 行），沒有越界，沒有程式變更
- 上一輪 2 項必改：
  1. `docs/development-spec.md:1952`：「延遲門檻成立」已改成「部分證實」，並附上扣掉第 1 篇只剩 35 則、低於下限，與報告第 1 節第 7 行一致：已修
  2. `docs/reports/bbs-spike.md:12`：已改成「門檻 1 因此只算部分證實」，與表格一致：已修
- 上一輪「不列為必改」的 2 項也一起改了：第 1 行改成「BBS 延遲看起來夠快（樣本部分證實）」；第 23 行 N=3 補上「同門檻 1，部分證實」
- 全文一致性：`grep -nE "延遲門檻成立|夠即時|門檻 1 (的)?成立" docs` 沒有結果。第 36 行「P1 … BBS 本身即時」講的是 P1（41 則，達下限 30），不是門檻 1 的 P2，不算矛盾
- 秘密與個資：`grep -rniE "PTT_BBS_(USERNAME|PASSWORD)=." docs`（worktree）沒有結果（rc=1）
- 甲方提供的事實（家用網路、與爬蟲共用對外 IP）上一輪已寫進第 3、8 節，這輪沒有改動；summary.json 口徑不一致已開 backlog #327，這張單不處理

## CI（給 manager）

- 這次 head 的 run 42566622103：Security 失敗，但不是這張單造成的。job log 顯示 gitleaks 的結果是「no leaks found」；失敗的是下一步下載 osv-scanner 時 GitHub 回 `curl: (22) … error: 504`，屬於暫時性的基礎設施錯誤，重跑那個 job 就可以。review 當下 Check 還在跑，Integration Test 已通過
- 前一次 run 42566267765（da79045）的 Security 也失敗；那次的 log 沒有讀，重跑後如果還是失敗，再請人調查
