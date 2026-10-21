"""開發規格 7.26 做法 8／威脅表：Kafka、ClickHouse 重置前須確認目標是測試服務（與 PG 同級）。

NOTE: 「測試目標」的規則規格未明訂；這裡只斷言最小集合：
開發／正式環境的主機與非測試 DB 必須被拒絕，且拒絕時不得刪除任何東西。
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from radar.common.settings import ClickHouseSettings, KafkaSettings
from tests.helpers import clickhouse as ch_helper
from tests.integration import conftest as it_conftest

REFUSE = (pytest.exit.Exception, SystemExit, ValueError, RuntimeError, PermissionError)

NON_TEST_KAFKA = ["kafka.dev.example.com:9092", "prod-kafka:9092", "10.20.30.40:9092"]
NON_TEST_CH = [
    ("http://clickhouse.dev.example.com:8123", "radar"),
    ("http://prod-clickhouse:8123", "radar"),
    ("http://localhost:8123", "radar_prod"),
]


@pytest.mark.parametrize("bootstrap", NON_TEST_KAFKA)
def test_reset_kafka_non_test_target_refuses_without_deleting(bootstrap: str) -> None:
    admin = MagicMock()
    admin.list_topics.return_value.topics = {"orders": object(), "alerts": object()}
    with (
        patch.object(it_conftest, "AdminClient", return_value=admin),
        patch.object(it_conftest, "RESET_TIMEOUT_S", 0.5),
        pytest.raises(REFUSE),
    ):
        it_conftest.reset_kafka(KafkaSettings(bootstrap_servers=bootstrap, client_id="it"))
    admin.delete_topics.assert_not_called()
    admin.create_topics.assert_not_called()


@pytest.mark.parametrize(("url", "db"), NON_TEST_CH)
def test_drop_databases_non_test_target_refuses_without_dropping(url: str, db: str) -> None:
    client = MagicMock()
    client.execute.return_value = "radar\ndev_data\nsystem"
    settings = ClickHouseSettings(url=url, db=db, user="radar", password=SecretStr("it"))
    with patch.object(ch_helper, "ClickHouseClient", return_value=client), pytest.raises(REFUSE):
        ch_helper.drop_databases(settings)
    sent = [str(c.args[0]) for c in client.execute.call_args_list]
    assert not any("DROP" in s.upper() for s in sent)
    assert not any("CREATE" in s.upper() for s in sent)
