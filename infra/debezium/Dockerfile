# Kafka Connect + Debezium，加上 Apicurio 的 Avro converter（設計文件 6.1）
# 版本組合經 S2-01 驗證；升級時重跑設計文件 6.2 的檢查
ARG DEBEZIUM_VERSION=3.7.0.Final
ARG APICURIO_VERSION=3.3.3

# NOTE: converter 3.x 以 tar.gz 發佈（內含全部相依 jar），不是單一 jar
FROM maven:3.9-eclipse-temurin-21 AS converter
ARG APICURIO_VERSION
WORKDIR /tmp/build
RUN echo "<project><modelVersion>4.0.0</modelVersion><groupId>radar</groupId><artifactId>download</artifactId><version>1</version><dependencies><dependency><groupId>io.apicurio</groupId><artifactId>apicurio-registry-distro-connect-converter</artifactId><version>${APICURIO_VERSION}</version><type>tar.gz</type></dependency></dependencies></project>" > pom.xml \
    && mvn -q dependency:copy-dependencies -DoutputDirectory=/tmp/dl \
    && mkdir /tmp/apicurio && tar -xzf /tmp/dl/*.tar.gz -C /tmp/apicurio

FROM quay.io/debezium/connect:${DEBEZIUM_VERSION}
COPY --from=converter /tmp/apicurio /kafka/connect/apicurio
