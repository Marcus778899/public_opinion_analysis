# Java（Maven／Gradle）工具對照

| 用途 | 建議 | 備註 |
|---|---|---|
| 測試 | JUnit 5；整合測試在 compose 的 `test` 服務裡連 compose 的 DB（本機 Testcontainers 在 sandbox 裡不能用） | Spring 專案用 `@SpringBootTest` 只在整合測試，單元測試不起 context |
| 覆蓋率 | JaCoCo（Maven `jacoco-maven-plugin`、Gradle `jacoco`），要產出 XML 報表 | Gradle 要設 `reports { xml.required = true }`；CI 的 `COVERAGE_SRC_ROOTS` 要填原始碼目錄 |
| lint／格式 | Spotless（google-java-format）、Checkstyle 或 PMD | |
| migration | Flyway 或 Liquibase | Flyway 免費版沒有 undo：down 寫成另一支「反向」migration，或在 PR 說明不可逆的理由 |
| 驗證 | Jakarta Bean Validation（`@Valid`、`@NotBlank`…）在 controller 邊界 | |
| 相依稽核 | CI 的 osv-scanner 會讀 `pom.xml`／Gradle lockfile；Gradle 要開 dependency locking 才掃得到遞移相依 | |

## `make coverage`（JaCoCo XML 寫到 `coverage-reports/`）

```make
coverage:
	mvn -q verify
	mkdir -p coverage-reports
	cp target/site/jacoco/jacoco.xml coverage-reports/java.xml
```

Gradle：`./gradlew test jacocoTestReport`，XML 在 `build/reports/jacoco/test/jacocoTestReport.xml`。
JaCoCo 報告只有套件與檔名，diff-cover 要知道原始碼目錄才對得回 repo：CI 的 `COVERAGE_SRC_ROOTS` 填 `src/main/java`（子目錄就是 `backend/src/main/java`），本機用 `--src-roots`。
