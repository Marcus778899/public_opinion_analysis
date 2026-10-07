from radar.common.kafka.config import MAX_MESSAGE_BYTES, consumer_config, producer_config
from radar.common.settings import KafkaSettings

SETTINGS = KafkaSettings(bootstrap_servers="k1:9092,k2:9094", client_id="test")


def test_producer_config_enables_idempotence_and_acks_all():
    cfg = producer_config(SETTINGS)

    assert cfg["acks"] == "all"
    assert cfg["enable.idempotence"] is True


def test_producer_config_uses_zstd():
    assert producer_config(SETTINGS)["compression.type"] == "zstd"


def test_producer_config_allows_raw_html_size():
    assert producer_config(SETTINGS)["message.max.bytes"] == MAX_MESSAGE_BYTES == 5 * 1024 * 1024


def test_consumer_config_disables_auto_commit():
    cfg = consumer_config(SETTINGS, "ingest")

    assert cfg["enable.auto.commit"] is False
    assert cfg["group.id"] == "ingest"


def test_consumer_config_starts_from_earliest():
    assert consumer_config(SETTINGS, "g")["auto.offset.reset"] == "earliest"


def test_configs_pass_bootstrap_servers_through():
    assert producer_config(SETTINGS)["bootstrap.servers"] == "k1:9092,k2:9094"
    assert consumer_config(SETTINGS, "g")["bootstrap.servers"] == "k1:9092,k2:9094"
