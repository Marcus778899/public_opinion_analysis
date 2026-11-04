"""驗收 replay-alert-repro 回歸（QA FAIL）：7.20 暖機後再 surge 不可誤報「topic 有舊訊息」。

in-process；Kafka 用有狀態的 fake：producer 送出的訊息會讓 topic 的 high watermark 增加。
"""

import base64
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from radar.common.log import log
from radar.streaming import replay as replay_mod
from radar.streaming.replay import RecordedMessage

POST = "Gossiping.M.1000000001.A.BBB"
WARNING_KEYWORD = "old messages"


class FakeTopic:
    def __init__(self, existing: int = 0) -> None:
        self.count = existing


def _fake_consumer_cls(topic: FakeTopic) -> Any:
    class FakeConsumer:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def list_topics(self, name: str, timeout: float = 0) -> Any:
            return SimpleNamespace(topics={name: SimpleNamespace(partitions={0: object()})})

        def get_watermark_offsets(self, *_a: object, **_k: object) -> tuple[int, int]:
            return 0, topic.count

        def close(self) -> None:
            pass

    return FakeConsumer


def _fake_producer_cls(topic: FakeTopic) -> Any:
    class FakeProducer:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def produce(self, *_a: object, **_k: object) -> None:
            topic.count += 1

        def poll(self, *_a: object, **_k: object) -> int:
            return 0

        def flush(self, *_a: object, **_k: object) -> int:
            return 0

    return FakeProducer


@pytest.fixture
def kafka(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    request: pytest.FixtureRequest,
):
    def setup(existing: int) -> FakeTopic:
        topic = FakeTopic(existing)
        monkeypatch.setattr(replay_mod, "setup_logging", lambda *_a, **_k: None)
        monkeypatch.setattr(replay_mod, "Consumer", _fake_consumer_cls(topic))
        monkeypatch.setattr(replay_mod, "Producer", _fake_producer_cls(topic))
        monkeypatch.setattr(replay_mod, "SchemaRegistryClient", MagicMock())
        monkeypatch.setattr(replay_mod, "SchemaRegistrySettings", MagicMock())
        for name in ("get_kafka_settings", "consumer_config", "producer_config"):
            monkeypatch.setattr(replay_mod, name, MagicMock())

        def fake_surge(producer: Any, _registry: object, events: list[dict[str, object]]) -> int:
            for _ in events:
                producer.produce("t")
            return len(events)

        monkeypatch.setattr(replay_mod, "surge", fake_surge)
        # loggerhelper 第一次寫 log 才建 logger，且 propagate=False，caplog 抓不到；
        # 先初始化再把 caplog 的 handler 掛到它自己的 logger 上
        log.info("init")
        lh_logger = logging.getLogger("loggerhelper")
        lh_logger.addHandler(caplog.handler)
        request.addfinalizer(lambda: lh_logger.removeHandler(caplog.handler))
        return topic

    return setup


def _write_recording(path: Path, n: int = 3) -> Path:
    msgs = [
        RecordedMessage(1_000 + i, base64.b64encode(b"k").decode(), base64.b64encode(b"v").decode())
        for i in range(n)
    ]
    path.write_text("\n".join(m.to_json() for m in msgs) + "\n")
    return path


def _run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> None:
    monkeypatch.setattr(sys, "argv", ["replay", *argv])
    replay_mod.main()


def _dirty_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if WARNING_KEYWORD in r.getMessage()]


def test_surge_after_warmup_replay_no_dirty_topic_warning(
    kafka: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    topic = kafka(existing=0)
    rec = _write_recording(tmp_path / "rec.jsonl")
    _run(monkeypatch, "replay", "--file", str(rec), "--speed", "1000")
    assert topic.count == 3
    before = len(_dirty_warnings(caplog))

    _run(monkeypatch, "surge", "--post-id", POST, "--count", "5")

    assert _dirty_warnings(caplog)[before:] == []


def test_replay_on_topic_with_leftovers_before_warmup_still_warns(
    kafka: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    kafka(existing=7)
    rec = _write_recording(tmp_path / "rec.jsonl")

    _run(monkeypatch, "replay", "--file", str(rec), "--speed", "1000")

    assert len(_dirty_warnings(caplog)) == 1
