# Grafana + ClickHouse plugin（開發規格 7.25）；plugin 在建置時裝進 image，執行時不連網、版本不會自己變
# NOTE: 預設值只為避免 InvalidDefaultArgInFrom；真正版本由 compose build args 傳入（來源 .env），沒傳會因 tag 不存在而建置失敗
ARG GRAFANA_VERSION=unset-use-compose-build-arg
FROM grafana/grafana-oss:${GRAFANA_VERSION}

ARG GRAFANA_CLICKHOUSE_PLUGIN_VERSION

# NOTE: 裝在資料目錄（/var/lib/grafana）之外，掛 volume 或 tmpfs 時才不會把 plugin 蓋掉
USER root
RUN mkdir -p /opt/grafana-plugins \
    && grafana cli --pluginsDir /opt/grafana-plugins plugins install grafana-clickhouse-datasource ${GRAFANA_CLICKHOUSE_PLUGIN_VERSION} \
    && chown -R 472:0 /opt/grafana-plugins
USER 472

# 關閉啟動時的 plugin 預裝與自動更新、更新檢查（離線也能啟動）
ENV GF_PATHS_PLUGINS=/opt/grafana-plugins \
    GF_PLUGINS_PREINSTALL_DISABLED=true \
    GF_PLUGINS_PREINSTALL_AUTO_UPDATE=false \
    GF_ANALYTICS_CHECK_FOR_UPDATES=false \
    GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false \
    GF_ANALYTICS_REPORTING_ENABLED=false \
    GF_DATE_FORMATS_DEFAULT_TIMEZONE=Asia/Taipei
