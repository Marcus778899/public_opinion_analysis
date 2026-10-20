# Dashboard Grafana 調查（7.25 方案 A）

**結論**（只整理事實，不做決策）
1. Grafana 穩定版：GitHub 標 Latest 為 13.2.4；plugin 最新 4.23.0（需 Grafana >=11.6.0-0）；26.8 相容性查不到；Grafana image 有 arm64，plugin 平台查不到。
2. 官方現行用 `GF_PLUGINS_PREINSTALL_SYNC`（`GF_PLUGINS_INSTALL` 自 v12.1.0 deprecated）；離線重啟沿用 volume 內 plugin 的行為官方查不到，需實測。
3. `$__timeFilter` 在 DateTime64(6) 的精度來源說法不一致，需實測；`from_env` 有官方說明；26.9 起 users.xml 的 `GRANT SYSTEM RELOAD MODEL` 會讓啟動失敗，26.8 的 `<grants>` 行為查不到。

**1. 版本與 arm64**
- Grafana：「13.2.4」標示 "Latest"（https://github.com/grafana/grafana/releases）
- Docker Hub 列 `13.0.2`、OS/ARCH 含 "linux/arm64"，與 GitHub 不一致（https://hub.docker.com/r/grafana/grafana-oss/tags）
- Plugin：「Current version: 4.23.0」、「Last updated 19 Oct 2026.」、「Grafana >=11.6.0-0」；未列 ClickHouse 版本（https://grafana.com/grafana/plugins/grafana-clickhouse-datasource）
- ClickHouse 26.8：「ClickHouse 26.8 LTS」，blog 日期 "Sep 10, 2026"（https://clickhouse.com/blog/clickhouse-release-26-08）
- 社群單一回報：Grafana 13.0.0 升級後 ClickHouse datasource 全部失敗（無官方回覆）（https://community.grafana.com/t/grafana-clickhouse-datasource-completely-broken-after-auto-upgrade-to-grafana-13-0-0/162274）

**2. Plugin 安裝**
- Method 2 格式 "<plugin ID>@[<plugin version>]@<url to plugin zip>"，可省略 version 與 URL（https://grafana.com/docs/grafana/latest/administration/plugin-management/plugin-install/）
- 標題 "Use `GF_PLUGINS_INSTALL` (Deprecated since v12.1.0)"（同上）
- 離線原文："Plugin installation usually requires an Internet connection."，建議改用 CLI 或 ZIP（同上）
- 重啟時已存在 plugin 是否跳過下載：官方查不到（https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/ 無 preinstall 設定說明）
- 社群稱預載 plugin 重啟會自動更新，未經官方核實（https://community.grafana.com/t/how-to-prevent-automatic-grafana-plugin-updates/157881）

**3. 巨集與 ClickHouse 設定**
- `$__timeFilter` 展開：plugin 現行頁為 Unix 秒的 `toDateTime`；舊鏡像為 `toDateTime64(…/1000, 3)`（搜尋摘要，未取原文）
- 官方建議 DateTime64 子秒用 `$__timeFilter_ms`（https://grafana.com/docs/plugins/grafana-clickhouse-datasource/latest/annotations/，僅搜尋摘要）
- 推論（未驗證）：若為秒級，DateTime64(6) 比較會截掉小數秒；macro 原頁 404
- `from_env`：「you can use the attribute `from_env`」，可加 `replace="1"` 設預設值（https://clickhouse.com/docs/concepts/features/configuration/server-config/configuration-files）
- `users.d`：「The directory `users.d` is used by default」，依完整路徑字典序合併（同上）
- `<grants>`：上述頁查不到；26.9 移除 `SYSTEM RELOAD MODEL`，users.xml 留有該行則啟動失敗（搜尋摘要，https://clickhouse.com/docs/en/whats_new/changelog/，未開原文）

**不確定處**
- Grafana 穩定版兩個來源不一致；plugin 與 26.8、plugin arm64 查不到
- 離線重啟行為、macro 精度、26.8 的 `<grants>` 皆需實測
