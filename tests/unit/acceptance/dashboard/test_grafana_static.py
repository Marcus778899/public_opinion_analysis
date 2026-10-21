"""驗收 dashboard-grafana-infra（開發規格 7.25 部署與權限、測試環境）的靜態檢查。

涵蓋 infra/docker-compose.yaml、compose.yaml、compose.ci.yaml、Dockerfile、
provisioning、grafana.xml、.env.example、ci.yml。測試環境的帳密鎖定為：
Grafana admin／admin 密碼 it，ClickHouse 唯讀帳號 grafana／it（同 conftest 的 PG、CH 作法）。
"""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ID = "grafana-clickhouse-datasource"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _read(rel: str) -> str:
    path = ROOT / rel
    assert path.is_file(), f"{rel} 不存在"
    return path.read_text()


def _yaml(rel: str) -> dict:
    data = yaml.safe_load(_read(rel))
    assert isinstance(data, dict)
    return data


def _blob(data: object) -> str:
    return json.dumps(data, ensure_ascii=False)


def _env(svc: dict) -> dict[str, str]:
    env = svc.get("environment", {})
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env)
    return {k: str(v) for k, v in env.items()}


def _env_example(var: str) -> str:
    m = re.search(rf"^{var}=(.*)$", _read(".env.example"), re.M)
    assert m, f"{var} 未在 .env.example 宣告（選填請用註解，見 D-009；本單的必填）"
    return m.group(1).strip().strip('"')


def _networks(svc: dict) -> set[str]:
    nets = svc.get("networks", [])
    return set(nets) if isinstance(nets, (list, dict)) else set()


def _dockerfile_path(svc: dict, base: str) -> Path:
    build = svc["build"]
    if isinstance(build, str):
        context, dockerfile = build, "Dockerfile"
    else:
        context, dockerfile = build.get("context", "."), build.get("dockerfile", "Dockerfile")
    return (ROOT / base / context / dockerfile).resolve()


def _mount_targets(svc: dict) -> dict[str, tuple[str, bool]]:
    """target -> (source, read_only)"""
    out: dict[str, tuple[str, bool]] = {}
    for v in svc.get("volumes", []):
        if isinstance(v, str):
            parts = v.split(":")
            out[parts[1]] = (parts[0], parts[-1] == "ro" and len(parts) > 2)
        else:
            out[v["target"]] = (v.get("source", ""), bool(v.get("read_only")))
    return out


@pytest.fixture(scope="module")
def dev() -> dict:
    return _yaml("infra/docker-compose.yaml")


@pytest.fixture(scope="module")
def compose() -> dict:
    return _yaml("compose.yaml")


@pytest.fixture(scope="module")
def compose_ci() -> dict:
    return _yaml("compose.ci.yaml")


@pytest.fixture(scope="module")
def ci() -> dict:
    return _yaml(".github/workflows/ci.yml")


# ---- 版本與環境變數 ----


@pytest.mark.parametrize("var", ["GRAFANA_VERSION", "GRAFANA_CLICKHOUSE_PLUGIN_VERSION"])
def test_env_example_pins_full_patch_version(var: str) -> None:
    assert SEMVER.match(_env_example(var)), "要完整 patch 號，不可 latest 或 13 這類浮動 tag"


@pytest.mark.parametrize(
    "var",
    [
        "GRAFANA_PORT",
        "GRAFANA_ADMIN_PASSWORD",
        "CLICKHOUSE_GRAFANA_USER",
        "CLICKHOUSE_GRAFANA_PASSWORD",
        "IT_GRAFANA_HOST_PORT",
    ],
)
def test_env_example_declares_grafana_variable(var: str) -> None:
    _env_example(var)


# ---- Dockerfile ----


def test_dockerfile_builds_from_pinned_grafana_oss_version_arg() -> None:
    text = _read("infra/grafana/Dockerfile")
    assert re.search(r"^ARG GRAFANA_VERSION\b", text, re.M)
    assert re.search(r"^FROM\s+grafana/grafana-oss:\$\{GRAFANA_VERSION\}", text, re.M)
    assert "latest" not in text.lower()


def test_dockerfile_installs_clickhouse_plugin_at_build_time_with_pinned_version() -> None:
    text = _read("infra/grafana/Dockerfile")
    assert re.search(r"^ARG GRAFANA_CLICKHOUSE_PLUGIN_VERSION\b", text, re.M)
    install = re.search(r"(grafana cli|grafana-cli)[^\n]*plugins install[^\n]*", text)
    assert install, "建置時要用 grafana cli 安裝 plugin"
    assert PLUGIN_ID in install.group(0)
    assert "${GRAFANA_CLICKHOUSE_PLUGIN_VERSION}" in install.group(0)


def test_dockerfile_disables_plugin_preinstall_and_auto_update() -> None:
    text = _read("infra/grafana/Dockerfile")
    assert re.search(r"GF_PLUGINS_PREINSTALL\w*", text), "要關閉啟動時的 plugin 預裝與自動更新"
    assert "GF_PLUGINS_PREINSTALL_SYNC" not in text, "不用啟動時下載"


# ---- infra/docker-compose.yaml（開發環境）----


def test_dev_grafana_builds_from_infra_dockerfile_with_version_args(dev: dict) -> None:
    svc = dev["services"]["grafana"]
    assert _dockerfile_path(svc, "infra") == (ROOT / "infra/grafana/Dockerfile").resolve()
    args = _blob(svc["build"].get("args", {}))
    assert "GRAFANA_VERSION" in args and "GRAFANA_CLICKHOUSE_PLUGIN_VERSION" in args


def test_dev_grafana_starts_with_default_profile(dev: dict) -> None:
    assert "profiles" not in dev["services"]["grafana"], "make up 要一併啟動"


def test_dev_grafana_binds_loopback_only(dev: dict) -> None:
    ports = [str(p) for p in dev["services"]["grafana"]["ports"]]
    assert len(ports) == 1
    assert re.fullmatch(r"127\.0\.0\.1:\$\{GRAFANA_PORT[^}]*\}:3000", ports[0]), ports


def test_dev_grafana_admin_password_is_required_without_default(dev: dict) -> None:
    env = _env(dev["services"]["grafana"])
    assert "${GRAFANA_ADMIN_PASSWORD:?" in env["GF_SECURITY_ADMIN_PASSWORD"]
    assert "admin/admin" not in _blob(dev["services"]["grafana"])


def test_dev_grafana_disables_anonymous_and_sign_up(dev: dict) -> None:
    env = _env(dev["services"]["grafana"])
    assert env.get("GF_AUTH_ANONYMOUS_ENABLED", "").lower() == "false"
    assert env.get("GF_USERS_ALLOW_SIGN_UP", "").lower() == "false"


def test_dev_grafana_uses_named_volume_and_mounts_provisioning_read_only(dev: dict) -> None:
    svc = dev["services"]["grafana"]
    mounts = _mount_targets(svc)
    assert mounts["/var/lib/grafana"][0] == "grafana_data"
    assert "grafana_data" in dev["volumes"]
    prov = [t for t, (src, ro) in mounts.items() if "grafana/provisioning" in src]
    dash = [t for t, (src, ro) in mounts.items() if src.rstrip("/").endswith("grafana/dashboards")]
    assert prov and dash
    assert all(mounts[t][1] for t in prov + dash), "provisioning 與 dashboards 要唯讀掛入"


def test_dev_grafana_receives_clickhouse_readonly_credentials(dev: dict) -> None:
    text = _blob(_env(dev["services"]["grafana"]))
    assert "CLICKHOUSE_GRAFANA_USER" in text and "CLICKHOUSE_GRAFANA_PASSWORD" in text


def test_dev_clickhouse_gets_readonly_user_settings_and_users_file(dev: dict) -> None:
    svc = dev["services"]["clickhouse"]
    env = _blob(_env(svc))
    assert "CLICKHOUSE_GRAFANA_PASSWORD" in env
    targets = _mount_targets(svc)
    assert "/etc/clickhouse-server/users.d/grafana.xml" in targets
    assert targets["/etc/clickhouse-server/users.d/grafana.xml"][1], "要唯讀掛入"
    assert "/etc/clickhouse-server/users.d/radar.xml" in targets, "既有的檔案不可被蓋掉"


def test_dev_grafana_waits_for_clickhouse(dev: dict) -> None:
    dep = dev["services"]["grafana"].get("depends_on", {})
    assert "clickhouse" in dep


# ---- compose.yaml（測試環境）----


def test_test_grafana_uses_same_dockerfile_as_dev(compose: dict, dev: dict) -> None:
    test_path = _dockerfile_path(compose["services"]["grafana"], ".")
    dev_path = _dockerfile_path(dev["services"]["grafana"], "infra")
    assert test_path == dev_path == (ROOT / "infra/grafana/Dockerfile").resolve()


def test_test_grafana_build_args_require_versions(compose: dict) -> None:
    args = _blob(compose["services"]["grafana"]["build"]["args"])
    assert "${GRAFANA_VERSION:?" in args
    assert "${GRAFANA_CLICKHOUSE_PLUGIN_VERSION:?" in args


def test_test_grafana_only_joins_internal_network(compose: dict) -> None:
    assert _networks(compose["services"]["grafana"]) == {"grafana_offline"}
    assert compose["networks"]["grafana_offline"].get("internal") is True


def test_test_grafana_publishes_no_port_and_has_no_container_name(compose: dict) -> None:
    svc = compose["services"]["grafana"]
    assert "ports" not in svc and "container_name" not in svc


def test_test_grafana_stores_data_on_tmpfs(compose: dict) -> None:
    svc = compose["services"]["grafana"]
    has = bool(svc.get("tmpfs")) or any(
        isinstance(v, dict) and v.get("type") == "tmpfs" for v in svc.get("volumes", [])
    )
    assert has
    assert "grafana_data" not in _blob(svc.get("volumes", []))


def test_test_grafana_mounts_provisioning_and_dashboards_read_only(compose: dict) -> None:
    mounts = _mount_targets(compose["services"]["grafana"])
    prov = [t for t, (s, _) in mounts.items() if "infra/grafana/provisioning" in s]
    dash = [t for t, (s, _) in mounts.items() if s.rstrip("/").endswith("infra/grafana/dashboards")]
    assert prov and dash
    assert all(mounts[t][1] for t in prov + dash)


def test_test_grafana_has_fixed_test_credentials_not_from_dotenv(compose: dict) -> None:
    env = _env(compose["services"]["grafana"])
    assert env["GF_SECURITY_ADMIN_PASSWORD"] == "it"
    assert env.get("GF_AUTH_ANONYMOUS_ENABLED", "").lower() == "false"
    assert env["CLICKHOUSE_GRAFANA_USER"] == "grafana"
    assert env["CLICKHOUSE_GRAFANA_PASSWORD"] == "it"
    assert "${" not in env["GF_SECURITY_ADMIN_PASSWORD"]


def test_test_grafana_has_healthcheck(compose: dict) -> None:
    assert compose["services"]["grafana"].get("healthcheck", {}).get("test")


def test_test_clickhouse_and_test_join_default_and_offline_networks(compose: dict) -> None:
    for name in ("clickhouse", "test"):
        nets = _networks(compose["services"][name])
        assert {"default", "grafana_offline"} <= nets, name
    for name in ("kafka", "postgres"):
        assert "grafana_offline" not in _networks(compose["services"][name]), name


def test_test_clickhouse_mounts_grafana_users_file_with_fixed_credentials(
    compose: dict,
) -> None:
    svc = compose["services"]["clickhouse"]
    targets = _mount_targets(svc)
    key = "/etc/clickhouse-server/users.d/grafana.xml"
    assert key in targets and targets[key][1]
    assert "infra/clickhouse/users.d/grafana.xml" in targets[key][0]
    assert "/etc/clickhouse-server/users.d/radar.xml" in targets
    env = _env(svc)
    assert env["CLICKHOUSE_GRAFANA_USER"] == "grafana"
    assert env["CLICKHOUSE_GRAFANA_PASSWORD"] == "it"
    # NOTE: 只能單檔掛入，整個目錄會蓋掉 image 的設定
    assert all(not t.rstrip("/").endswith("users.d") for t in targets)


def test_test_service_waits_for_healthy_grafana_and_receives_its_url(compose: dict) -> None:
    svc = compose["services"]["test"]
    assert svc["depends_on"]["grafana"]["condition"] == "service_healthy"
    assert _env(svc)["IT_GRAFANA_URL"] == "http://grafana:3000"


def test_test_service_receives_versions_for_compatibility_checks(compose: dict) -> None:
    text = _blob(_env(compose["services"]["test"]))
    for var in ("GRAFANA_VERSION", "GRAFANA_CLICKHOUSE_PLUGIN_VERSION"):
        assert var in text, var


def test_test_service_has_fixed_grafana_and_clickhouse_credentials(compose: dict) -> None:
    env = _env(compose["services"]["test"])
    assert env["GRAFANA_ADMIN_PASSWORD"] == "it"
    assert env["CLICKHOUSE_GRAFANA_USER"] == "grafana"
    assert env["CLICKHOUSE_GRAFANA_PASSWORD"] == "it"


# ---- compose.ci.yaml、ci.yml、conftest ----


def test_ci_override_binds_grafana_port_to_loopback_and_adds_default_network(
    compose_ci: dict,
) -> None:
    svc = compose_ci["services"]["grafana"]
    ports = [str(p) for p in svc["ports"]]
    assert any(
        p.startswith("127.0.0.1:${IT_GRAFANA_HOST_PORT") and p.endswith(":3000") for p in ports
    )
    assert {"default", "grafana_offline"} <= _networks(svc)


def test_ci_starts_grafana_with_other_services(ci: dict) -> None:
    texts = [_blob(s) for s in ci["jobs"]["integration"]["steps"]]
    up = [t for t in texts if "up -d --wait" in t]
    assert up and all("grafana" in t for t in up)


def test_ci_points_it_grafana_url_at_localhost(ci: dict) -> None:
    joined = _blob(ci["jobs"]["integration"])
    assert re.search(r"IT_GRAFANA_URL=\\?\"?http://(127\.0\.0\.1|localhost):", joined)
    assert "IT_GRAFANA_HOST_PORT" in joined


def test_integration_conftest_requires_it_grafana_url() -> None:
    text = _read("tests/integration/conftest.py")
    required = re.search(r"REQUIRED_ENV\s*=\s*\((.*?)\)", text, re.S)
    assert required and "IT_GRAFANA_URL" in required.group(1)


# ---- ClickHouse 唯讀帳號設定 ----


def _users_xml() -> ET.Element:
    return ET.fromstring(_read("infra/clickhouse/users.d/grafana.xml"))


def test_grafana_users_file_reads_password_from_env_without_plaintext() -> None:
    root = _users_xml()
    pw = [e for e in root.iter() if e.get("from_env") == "CLICKHOUSE_GRAFANA_PASSWORD"]
    assert pw, "密碼要以 from_env 讀"
    assert all(not (e.text or "").strip() for e in pw)


def test_grafana_users_file_is_readonly_and_limited_to_one_database() -> None:
    text = ET.tostring(_users_xml(), encoding="unicode")
    assert re.search(r"<readonly>\s*1\s*</readonly>", text)
    assert re.search(
        r"<allow_databases>.*?<database[^>]*>(\$\{CLICKHOUSE_DB\}|radar)<", text, re.S
    ) or ("allow_databases" in text and 'from_env="CLICKHOUSE_DB"' in text)


def test_grafana_users_file_sets_execution_and_memory_limits() -> None:
    root = _users_xml()
    for tag in ("max_execution_time", "max_memory_usage"):
        found = [e for e in root.iter(tag) if (e.text or "").strip().isdigit()]
        assert found and int(found[0].text.strip()) > 0, tag


def test_grafana_users_file_grants_no_named_collection_or_grants_block() -> None:
    text = _read("infra/clickhouse/users.d/grafana.xml")
    no_comments = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    assert "named_collection_control" not in no_comments
    assert "show_named_collections" not in no_comments
    assert "<grants" not in no_comments, "26.8 的 <grants> 行為查不到官方說明（7.25）"


# ---- provisioning ----


def test_datasource_provisioning_uses_fixed_uid_and_plugin_type() -> None:
    data = _yaml("infra/grafana/provisioning/datasources/clickhouse.yaml")
    assert data["apiVersion"] == 1
    ds = {d["uid"]: d for d in data["datasources"]}
    assert ds["radar-clickhouse"]["type"] == PLUGIN_ID


def test_datasource_provisioning_has_no_plaintext_credentials() -> None:
    data = _yaml("infra/grafana/provisioning/datasources/clickhouse.yaml")
    d = next(x for x in data["datasources"] if x["uid"] == "radar-clickhouse")
    secrets = [d.get("user"), d.get("password"), d.get("basicAuthPassword")]
    secrets += list((d.get("secureJsonData") or {}).values())
    secrets += [(d.get("jsonData") or {}).get("username")]
    secrets = [str(s) for s in secrets if s]
    assert secrets, "datasource 要帶唯讀帳號"
    assert all("$" in s for s in secrets), secrets
    text = _blob(d)
    assert "CLICKHOUSE_GRAFANA_PASSWORD" in text and "CLICKHOUSE_GRAFANA_USER" in text
    assert "CLICKHOUSE_PASSWORD" not in text.replace("CLICKHOUSE_GRAFANA_PASSWORD", "")


def test_datasource_provisioning_is_not_editable_from_ui() -> None:
    data = _yaml("infra/grafana/provisioning/datasources/clickhouse.yaml")
    d = next(x for x in data["datasources"] if x["uid"] == "radar-clickhouse")
    assert d.get("editable") is False


def test_dashboard_provider_is_managed_by_provisioning_and_path_is_mounted(
    compose: dict, dev: dict
) -> None:
    data = _yaml("infra/grafana/provisioning/dashboards/radar.yaml")
    assert data["apiVersion"] == 1
    provider = data["providers"][0]
    assert provider["allowUiUpdates"] is False
    path = provider["options"]["path"].rstrip("/")
    for cfg in (compose, dev):
        mounts = _mount_targets(cfg["services"]["grafana"])
        targets = [
            t.rstrip("/")
            for t, (s, _) in mounts.items()
            if s.rstrip("/").endswith("grafana/dashboards")
        ]
        assert path in targets, (path, targets)
