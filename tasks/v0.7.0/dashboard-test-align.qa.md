PASS d0cf76f

# 驗證 dashboard-test-align（docs 單）

## 1. 只改 docs/development-spec.md
`git diff develop...HEAD --name-only` 輸出：
```
docs/development-spec.md
```
`git log develop..HEAD`：單一 commit d0cf76f。24 增 9 減，皆在該檔。

## 2. 7.25 不再依賴 testcontainers
`grep -n testcontainers docs/development-spec.md` 實際輸出的行號：39（1.1）、301（5 章）、1118、1142、1144、1145（皆在 7.26）。
7.25 範圍（1009–1115 行）沒有出現。39、301 屬 test-infra-compose 範圍（派工單已註明），未動。

## 3. 7.26 只動做法 1 服務清單
diff 在 7.26 區段只有一個 hunk（做法 1 那一列，補一句 grafana 由 dashboard-grafana-infra 之後加入、做法見 7.25「測試環境」）。其餘（做法 2、10、15、xdist 隔離表、風險表）未動。

## 4. 與 7.26 其他做法一致
- xdist 隔離：7.25 的「測試查詢的 DB」用 `radar` DB、uuid 看板名稱，不用 `radar_<worker>`。7.26 隔離表也有「依賴 Kafka engine 的測試用 `radar` DB」，且 `radar` 的全域重置只在主程序做，所以不衝突。
- 做法 2 的 IT_* 必填：7.25 明寫 IT_GRAFANA_URL 併入該清單（缺就 pytest.exit），7.26 清單本身未改，由後續單補。
- 做法 10 CI：7.25 的 compose.ci.yaml 綁 127.0.0.1:${IT_GRAFANA_HOST_PORT}，`up -d --wait` 加 grafana，與做法 10 的 compose.ci.yaml 作法一致。限制已寫明：只接 internal network 的容器無法發布 port，CI 綠燈不構成離線證據，離線只由 `run --rm test` 證明。
- 7.26 風險表 users.d 列（1206 行）與 7.25 的「測試用帳密」固定值一致。
- 派工順序 1→2→3→4 與「1 要在 test-infra-compose 之後」一致；負責檔案 compose.yaml、compose.ci.yaml、conftest.py、ci.yml 與 7.25 測試環境表對得上。

## 5. 驗收條件
- [x] 7.25 派工順序表（1、2、4 列）與 test_grafana_infra.py 表已改寫，7.25 無 testcontainers；「離線啟動」列改為透過 IT_GRAFANA_URL。
- [x] 7.26 做法 1 補上 grafana；CI 覆寫檔與離線檢查的限制寫在 7.25「測試環境」的 CI、離線檢查的限制兩列。
- [x] 回報 open_questions 列出自行決定的變更；7.25「自行決定」表同步新增 3 列；沒有新的待決定。

## 6. 設定值
文件只寫變數名稱（IT_GRAFANA_URL、IT_GRAFANA_HOST_PORT、GRAFANA_VERSION…）。`http://grafana:3000` 是 compose 內部服務位址，不是機器設定；測試用固定帳密以文字描述，沒有實際值。

## 觀察（非 FAIL，供 manager 參考）
- 7.26 風險表 users.d 列仍寫「後合併的一方補」，7.25 已能確定是 dashboard-grafana-infra。本單禁區不能改，開 dashboard-grafana-infra 單時要提醒。
- 7.26 做法 8 寫「各模組開始時清自己用的表」。dashboard 測試共用 `radar` DB，worker 實作時要避免清到別人的種子資料（已有 uuid 隔離）。
