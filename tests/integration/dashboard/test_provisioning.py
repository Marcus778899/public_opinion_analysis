"""provisioning 的 dashboard 與 6 個面板查詢，經 Grafana /api/ds/query 在真的 plugin 上可用。"""

import pytest

from tests.integration.dashboard._dash import (
    ALL_PANELS,
    DS,
    P_VOLUME,
    load_dashboard,
    run_panel,
    seed_board_with_comment,
)

# NOTE: 其他模組會 TRUNCATE radar 的資料表，同組固定在同一個 worker 才不會把種子資料清掉
pytestmark = pytest.mark.xdist_group("shared_radar_db")


@pytest.fixture(scope="module")
def dashboard() -> dict:
    return load_dashboard()


def test_provisioned_dashboard_exists_with_six_panels(dashboard: dict) -> None:
    titles = [p["title"] for p in dashboard["panels"]]
    for title in ALL_PANELS:
        assert titles.count(title) == 1, titles
    assert dashboard["uid"] == "radar"


def test_provisioned_dashboard_is_not_editable(dashboard: dict) -> None:
    assert dashboard.get("editable") is False


@pytest.mark.parametrize("title", ALL_PANELS)
def test_panel_query_runs_through_plugin_without_error(dashboard: dict, title: str) -> None:
    seeded = seed_board_with_comment()
    run_panel(dashboard, title, [seeded.board])


def test_panel_query_returns_seeded_comment_through_plugin(dashboard: dict) -> None:
    seeded = seed_board_with_comment()
    rows = run_panel(dashboard, P_VOLUME, [seeded.board])
    assert rows, "面板 1 經 plugin 沒有任何資料"


def test_panels_use_provisioned_datasource_uid(dashboard: dict) -> None:
    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            assert (target.get("datasource") or panel["datasource"])["uid"] == DS["uid"]
