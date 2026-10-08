import httpx2
from pydantic import SecretStr

from radar.common.clickhouse import ClickHouseClient
from radar.common.settings import ClickHouseSettings

SETTINGS = ClickHouseSettings(url="http://ch:8123", db="radar", user="u", password=SecretStr("p"))


def client_returning(body: str, seen: dict) -> ClickHouseClient:
    def handler(request):
        seen["params"] = dict(request.url.params)
        seen["sql"] = request.content.decode()
        return httpx2.Response(200, text=body)

    return ClickHouseClient(SETTINGS, transport=httpx2.MockTransport(handler))


def test_execute_sends_params_as_query_string():
    seen: dict = {}

    client_returning("", seen).execute(
        "SELECT * FROM t WHERE board = {board:String}", {"board": "Stock"}
    )

    assert seen["params"] == {"database": "radar", "param_board": "Stock"}
    assert "Stock" not in seen["sql"]


def test_query_rows_parses_json_each_row():
    seen: dict = {}
    body = '{"post_id":"a","n":1}\n{"post_id":"b","n":2}\n'

    rows = client_returning(body, seen).query_rows("SELECT post_id, n FROM t")

    assert rows == [{"post_id": "a", "n": 1}, {"post_id": "b", "n": 2}]
    assert seen["sql"].endswith("FORMAT JSONEachRow")


def test_query_rows_empty_result_returns_empty_list():
    assert client_returning("", {}).query_rows("SELECT 1 WHERE 0") == []
