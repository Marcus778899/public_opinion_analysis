# pttbbs 同帳號多重登入：上限、畫面文字、被踢（G-9-1）

> 調查日 2026-11-09。來源為 GitHub `ptt/pttbbs` 的 `master` 分支 raw 檔（抓取時未取得 commit hash；行號對應該次抓取的檔案）。未連 ptt.cc / term.ptt.cc。

## 結論（3 行內）

1. pttbbs 原始碼**沒有** `MAX_MULTI` 這類數字上限；判斷是「是否已有其他連線」，超過時由使用者選擇是否踢掉舊連線。數字上限**查不到**。
2. 畫面文字（可信度中，見下）：警告「注意: 您有其它連線已登入此帳號。」＋提示「您想刪除其他重複登入的連線嗎？[Y/n]」；選 n 且仍有其他連線時，**無任何文字**，直接斷線。
3. 被踢的舊連線收到 SIGHUP 後直接結束，程式內**沒找到**伺服器送出的專用文字。建議（非定案）：M 階段關鍵字以「重複登入的連線」「其它連線已登入」為主，並以實機 log 驗證。

## 程式證據（mbbsd/mbbsd.c，master raw 抓取）

| 項目 | 原始碼位置 | 內容 | 可信度 |
|---|---|---|---|
| 判斷有無其他連線 | mbbsd/mbbsd.c:371-391 `getotherlogin(int num)` | 以 `search_ulistn(usernum, num)` 取第 num 個 session；略過 DEBUGSLEEPING、pid<=0、`kill(pid,0)<0` 者 | 中（raw 抓取，行號由 grep -n 取得） |
| 多重登入檢查 | mbbsd/mbbsd.c:393-437 `multi_user_check()` | 系統管理員（PERM_SYSOP）直接略過；僅 `cuser.userlevel != 0` 才檢查 | 中 |
| 呼叫點 | mbbsd/mbbsd.c:538-539 | `load_current_user()` 內 `multi_user_check();` | 中 |
| 「上限」字面值 | mbbsd/mbbsd.c:405, 418 `getotherlogin(1)`；431 `getotherlogin(3)`；434 | 1 = 有無其他連線；3 = 踢完後仍剩其他連線時的判斷。`search_ulistn` 的第二參數定義**沒找到**，無法換算成「幾條」 | 低（字面值，語意未證實） |
| 踢人動作 | mbbsd/mbbsd.c:421-426 | 對 `ui->pid` 送 `SIGHUP`，寫 log `log_usies("KICK ", cuser.nickname)` | 中 |
| 拒絕路徑 | mbbsd/mbbsd.c:432-437 | 選 n 且 `getotherlogin(3)` 仍非 NULL：`sleep(1); abort_bbs(0);`，無輸出文字 | 中 |
| 隨機延遲 | mbbsd/mbbsd.c:404, 414, 430 | 0~1 秒、0~5 秒、1~3 秒 usleep（防競態） | 中 |
| 其他站級上限 | mbbsd/mbbsd.c `check_ban_and_load`、logind `regular_check` | `SHM->UTMPnumber >= MAX_ACTIVE` 等，是**全站**滿載判斷，非單一帳號 | 中；畫面文字**沒找到** |

## 畫面文字

| 用途 | 文字 | 來源 | 可信度 |
|---|---|---|---|
| 超過/重複登入警告 | `注意: 您有其它連線已登入此帳號。` | mbbsd/mbbsd.c `multi_user_check`（經 GitHub blob 頁面轉述，見下） | 中（「其它」與「其他」用字需實機核對） |
| 踢掉舊連線的提示 | `您想刪除其他重複登入的連線嗎？[Y/n]` | 同上 | 中；2013 年一個自動登入腳本也引用近似字句（來源：<https://snippets.cacher.io/snippet/dfbd4b9ea13715fd2330>，舊、不可直接採信） |
| 被踢者的畫面 | 沒找到（SIGHUP → `abort_bbs`，`abort_bbs` 本身不印字） | mbbsd/mbbsd.c `abort_bbs()` 轉述 | 中低 |
| 超限被拒的畫面 | 沒找到（程式無輸出即斷線） | mbbsd/mbbsd.c:432-437 | 中 |
| 第三方客戶端的提示 | `您想踢掉其他重複的連線嗎？[Y/n]` | GhosPTT issue #5（<https://github.com/p47t/ghosptt/issues/5>，2026-11-08，客戶端筆記，未對照伺服器原始碼） | 低 |

說明：raw 檔中中文為 Big5 位元組，抓取後變成亂碼，無法直接讀字；上列中文字串取自 GitHub blob 頁面（<https://github.com/ptt/pttbbs/blob/master/mbbsd/mbbsd.c>）的渲染結果，為 WebFetch 小模型轉述，建議再以原檔位元組核對。

## PyPtt 2.3.16（本機 `.venv/lib/python3.12/site-packages/PyPtt`）

- 對整個套件以 `重複`、`其他連線`、`刪除`、`已登入`、`踢`、`kick`、`Y/n`、`您想`、`任意鍵`、`SIGHUP` 搜尋（不分大小寫）：**沒有任何命中**。
- 結論：PyPtt 沒有處理多重登入提示；遇到該提示時需由呼叫端自行處理（可信度中，依 grep 結果）。

## 查不到／限制

- MAX_MULTI 或同等上限數字：**沒找到**。GitHub 程式碼搜尋需登入，無法使用。
- `search_ulistn` 定義（第二參數語意）：**沒找到**（不在 mbbsd/user.c；未查 common/ 下的檔案）。
- 站上實際同時登入數：未實測（D-044）。

## 建議（非定案，供 architect 參考）

- M 階段立即停止的關鍵字：以 `重複登入的連線` 與 `其它連線已登入` 為候選；兩者都需實機 log 核對。
- 超限時可能**無文字**，只靠關鍵字偵測會漏抓，建議同時偵測「送出密碼後連線非預期斷開」。
- 原始碼未附 commit，報告引用時應補上抓取當天的 commit hash。
