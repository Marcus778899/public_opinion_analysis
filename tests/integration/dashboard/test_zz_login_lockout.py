"""回歸：錯誤密碼嘗試之後，正確帳密仍能通過認證（qa 問題 1，Grafana 暴力破解鎖定）。

acceptance 的錯誤密碼測試會對 admin 連續登入失敗；同一組堆疊不 down -v 連跑時，
鎖定讓 dashboard 測試的 setup 回 401。檔名 zz 讓單 worker 時排在最後。
"""

import base64
import json
import urllib.error
import urllib.request

import pytest

from tests.integration.dashboard._dash import GRAFANA_AUTH, grafana_url

pytestmark = pytest.mark.xdist_group("shared_radar_db")

WRONG_ATTEMPTS = 12  # 大於 Grafana 預設的登入失敗上限（5 次）


def _login_status(user: str, password: str) -> int:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(
        f"{grafana_url()}/api/user", headers={"Authorization": f"Basic {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            json.loads(resp.read().decode())
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def test_correct_credentials_still_authenticate_after_repeated_wrong_passwords() -> None:
    user, password = GRAFANA_AUTH
    statuses = [_login_status(user, f"wrong-{i}") for i in range(WRONG_ATTEMPTS)]
    assert all(s == 401 for s in statuses), f"錯誤密碼都應被拒絕：{statuses}"
    assert _login_status(user, password) == 200, "錯誤密碼嘗試後，正確帳密被鎖定（401）"
