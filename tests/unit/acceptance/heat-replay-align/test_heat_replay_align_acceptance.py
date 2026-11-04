"""驗收 heat-replay-align（#257，UAT v0.6.0 F-5、F-6、F-8）。

Kafka、Apicurio 一律用 fake／mock；只看 heat 建立的輸出 topic、replay surge 實際送出的事件、
開發規格 7.20 的回放步驟。
"""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from radar.common.kafka import names
from radar.common.settings import HeatSettings
from radar.streaming import heat
from radar.streaming import replay as replay_mod

ROOT = Path(__file__).resolve().parents[4]
POST_ID = "Stock.M.1792000000.A.ABC"


def _alert_topic_constants() -> dict[str, str]:
    return {
        k: v
        for k, v in vars(names).items()
        if k.isupper() and isinstance(v, str) and "alert" in v and v != names.ALERTS
    }


def _heat_topics(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> list[str]:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    app = MagicMock()
    monkeypatch.setattr(heat, "Application", lambda **_kw: app)
    heat.build_app(HeatSettings(), MagicMock(), MagicMock(), MagicMock())
    return [c.args[0] for c in app.topic.call_args_list]


# --- 驗收 1：輸出 topic 可設定 ---


def test_heat_default_output_is_production_alerts_topic(monkeypatch):
    # 守門：預設行為不變
    topics = _heat_topics(monkeypatch, {})
    assert names.ALERTS in topics
    assert set(_alert_topic_constants().values()).isdisjoint(topics)


def test_heat_output_topic_env_replaces_alerts_topic(monkeypatch):
    topics = _heat_topics(monkeypatch, {"HEAT_OUTPUT_TOPIC": "replay.alerts.custom"})
    assert "replay.alerts.custom" in topics
    assert names.ALERTS not in topics


def test_heat_input_topic_env_still_works(monkeypatch):
    # 守門：既有的輸入 topic 設定不被動到
    topics = _heat_topics(monkeypatch, {"HEAT_INPUT_TOPIC": "replay.cdc.comments"})
    assert "replay.cdc.comments" in topics
    assert names.ALERTS in topics


# --- 驗收 1：回放專用 topic，bot 不訂閱 ---


def test_names_has_replay_alerts_topic_distinct_from_production():
    found = _alert_topic_constants()
    assert found, "names.py 要有回放專用的 alerts topic 名稱（名稱含 alert，且不等於 ALERTS）"
    assert all(v.startswith("replay.") for v in found.values())


def test_bot_does_not_subscribe_to_replay_alerts_topic():
    bot_src = (ROOT / "src/radar/bot/main.py").read_text()
    assert "names.ALERTS" in bot_src  # 守門：bot 仍訂閱正式 alerts
    for const, value in _alert_topic_constants().items():
        assert f"names.{const}" not in bot_src
        assert value not in bot_src


# --- 驗收 2：surge 預設則數與補尾事件 ---


class FakeSerializer:
    def __init__(self, *_a: object, **_k: object) -> None:
        pass

    def __call__(self, event: dict, _ctx: object) -> bytes:
        return json.dumps(event).encode()


class FakeProducer:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def produce(self, topic: str, key=None, value=None, **_k: object) -> None:
        assert topic == names.REPLAY_COMMENTS
        self.sent.append(json.loads(value))

    def poll(self, _t: float) -> int:
        return 0

    def flush(self) -> int:
        return 0


def _run_surge(monkeypatch: pytest.MonkeyPatch, extra_args: list[str]) -> list[dict]:
    producer = FakeProducer()
    monkeypatch.setattr(replay_mod, "Producer", lambda _cfg: producer)
    monkeypatch.setattr(replay_mod, "AvroSerializer", FakeSerializer)
    monkeypatch.setattr(replay_mod, "SchemaRegistryClient", MagicMock())
    monkeypatch.setattr(replay_mod, "get_kafka_settings", MagicMock())
    monkeypatch.setattr(replay_mod, "producer_config", lambda _k: {})
    monkeypatch.setattr(replay_mod, "setup_logging", lambda _n: None)
    monkeypatch.setenv("SCHEMA_REGISTRY_URL", "http://fake")
    monkeypatch.setattr(sys, "argv", ["replay", "surge", "--post-id", POST_ID, *extra_args])
    replay_mod.main.__wrapped__() if hasattr(replay_mod.main, "__wrapped__") else replay_mod.main()
    return producer.sent


def _minute(event: dict) -> int:
    return int(event["__source_ts_ms"]) // 60_000


def test_surge_default_count_not_below_post_min_count(monkeypatch):
    sent = _run_surge(monkeypatch, [])
    assert len(sent) - 1 >= HeatSettings().post_min_count


def test_surge_default_count_follows_post_min_count_setting(monkeypatch):
    monkeypatch.setenv("HEAT_POST_MIN_COUNT", "150")
    sent = _run_surge(monkeypatch, [])
    assert len(sent) - 1 >= 150


def test_surge_adds_one_event_in_minute_after_the_burst(monkeypatch):
    sent = _run_surge(monkeypatch, [])
    last = max(_minute(e) for e in sent)
    in_last = [e for e in sent if _minute(e) == last]
    assert len(in_last) == 1
    assert all(_minute(e) < last for e in sent if e is not in_last[0])
    assert in_last[0]["__op"] == "c"


def test_surge_explicit_count_is_respected_plus_tail_event(monkeypatch):
    sent = _run_surge(monkeypatch, ["--count", "100", "--minutes", "2"])
    assert len(sent) in (100, 101)
    last = max(_minute(e) for e in sent)
    assert sum(1 for e in sent if _minute(e) == last) == 1


def test_surge_events_pure_function_unchanged_for_explicit_count():
    # 守門：既有純函式的契約不變
    events = replay_mod.surge_events(POST_ID, 1, 4, 2, datetime(2026, 10, 17, 3, 0, tzinfo=UTC))
    assert len(events) == 4


# --- 驗收 3：回放步驟每次用新的 consumer group ---


def _section_7_20() -> str:
    text = (ROOT / "docs/development-spec.md").read_text()
    start = text.index("**錄製與回放**")
    return text[start : start + 4000]


def test_spec_replay_steps_use_fresh_consumer_group_each_time():
    section = _section_7_20()
    assigns = re.findall(r"HEAT_CONSUMER_GROUP=(\S+)", section)
    assert assigns, "7.20 回放步驟要寫出 HEAT_CONSUMER_GROUP 的設定"
    for value in assigns:
        v = value.strip("`\"'")
        assert v != "heat-replay"
        assert re.search(r"\$|<|\{", v), f"consumer group 要含時間戳之類的動態部分：{v}"


def test_spec_replay_steps_point_alerts_to_replay_topic():
    section = _section_7_20()
    assert re.search(r"HEAT_OUTPUT_TOPIC=\S*replay", section)
