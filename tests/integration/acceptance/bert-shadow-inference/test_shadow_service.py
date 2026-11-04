"""bert-shadow-inference 驗收：以 main() 啟動推論服務，對真實 Kafka、ClickHouse（開發規格 7.27）。

只換掉不可在測試取得的外部件：Classifier（FakeClassifier）、Avro 解碼與 schema registry
（CdcPost 以 JSON 送出）。topic 每個測試各用一組，避免 xdist 的 worker 互相消費。
"""

import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from radar.common.enums import Polarity
from radar.common.kafka import names
from radar.common.kafka.config import admin_config, consumer_config
from radar.common.kafka.consumer import BatchConsumer
from radar.common.kafka.dlq import DLQ_TOPIC
from radar.common.kafka.producer import JsonProducer
from radar.common.schemas import DlqRecord, Prediction
from radar.common.settings import InferenceRole, InferenceSettings, get_kafka_settings
from radar.ml.inference import main as inference_main
from radar.ml.inference.main import text_hash
from radar.ml.inference.roles import ROLE_TARGETS, RoleTargets
from radar.ml.training.dataset import post_text
from radar.ml.training.train import ModelCard
from tests.unit.ml.fakes import FakeClassifier

TIMEOUT_S = 60
SENTINEL = "Stock.M.1792999999.A.END"
MAX_CHARS = 2000
OLD_HASH = "1" * 64


def make_card(model_version: str) -> ModelCard:
    # NOTE: 推論服務只用 model_version 與 max_chars，kind 用預設的 sklearn 即可
    return ModelCard(
        model_version=model_version,
        created_at=datetime(2026, 10, 21, tzinfo=UTC),
        dataset="it.jsonl",
        labeler="groq:q",
        label_version="prompt-v6",
        max_chars=MAX_CHARS,
        n_train=6,
        class_counts={"positive": 2, "negative": 2, "neutral": 2},
        params={},
    )


@dataclass
class Env:
    cdc: str
    primary_topic: str
    shadow_topic: str
    model_version: str
    classifier: FakeClassifier


@pytest.fixture
def env(monkeypatch, tmp_path: Path, kafka_settings, worker_clickhouse_settings, clickhouse):
    suffix = uuid.uuid4().hex[:8]
    e = Env(
        cdc=f"it.cdc.{suffix}",
        primary_topic=f"it.pred.{suffix}",
        shadow_topic=f"it.shadow.{suffix}",
        model_version=f"bert-it-{suffix}",
        classifier=FakeClassifier(),
    )
    admin = AdminClient(admin_config(kafka_settings))
    topics = (e.cdc, e.primary_topic, e.shadow_topic, DLQ_TOPIC)
    for name, future in admin.create_topics([NewTopic(t, 1, 1) for t in topics]).items():
        try:
            future.result()
        except Exception:
            if name != DLQ_TOPIC:  # dlq 可能已由其他測試建立
                raise
    # group、topic、表名只從 roles 對照表取：測試換成各自的 topic，表名維持
    monkeypatch.setitem(
        ROLE_TARGETS, InferenceRole.PRIMARY, RoleTargets(e.primary_topic, "predictions")
    )
    monkeypatch.setitem(
        ROLE_TARGETS, InferenceRole.SHADOW, RoleTargets(e.shadow_topic, "predictions_shadow")
    )
    monkeypatch.setattr(names, "CDC_POSTS", e.cdc)
    ch = worker_clickhouse_settings
    for key, value in {
        "KAFKA_BOOTSTRAP_SERVERS": kafka_settings.bootstrap_servers,
        "CLICKHOUSE_URL": ch.url,
        "CLICKHOUSE_DB": ch.db,
        "CLICKHOUSE_USER": ch.user,
        "CLICKHOUSE_PASSWORD": ch.password.get_secret_value(),
        "INFERENCE_MODEL_DIR": str(tmp_path),
        "INFERENCE_BATCH_SIZE": "10",
    }.items():
        monkeypatch.setenv(key, value)
    get_kafka_settings.cache_clear()
    card = make_card(e.model_version)
    (tmp_path / "model_card.json").write_text(card.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(
        inference_main,
        "load_classifier",
        lambda model_dir, *, threads, max_batch_tokens: (e.classifier, card),
        raising=False,
    )
    # CdcPost 以 JSON 送出：None 代表 BatchConsumer 的預設 JSON 解碼
    monkeypatch.setattr(inference_main, "make_avro_decoder", lambda model, registry: None)
    monkeypatch.setattr(
        inference_main.SchemaRegistryClient, "new_client", staticmethod(lambda conf: object())
    )
    clickhouse.execute("TRUNCATE TABLE predictions")
    clickhouse.execute("TRUNCATE TABLE predictions_shadow")
    return e


def produce_event(producer: JsonProducer, topic: str, post_id: str, op: str, content: str) -> None:
    value = {"post_id": post_id, "board": "Stock", "title": "t", "content": content, "__op": op}
    producer._producer.produce(topic, key=post_id.encode(), value=json.dumps(value).encode())


def run_service(monkeypatch, role: InferenceRole, kafka_settings, env: Env) -> None:
    """以指定角色跑 main() 直到處理到 SENTINEL 事件（已送出並 flush）後停止。"""
    monkeypatch.setenv("INFERENCE_ROLE", role.value)
    producer = JsonProducer(kafka_settings)
    produce_event(producer, env.cdc, SENTINEL, "c", "結束")
    producer.flush()
    done = threading.Event()

    class StoppingConsumer(BatchConsumer):
        def __init__(self, *args: object, handler: Callable, **kwargs: object) -> None:
            def wrapped(events):
                result = handler(events)
                if any(e.post_id == SENTINEL for e in events):
                    done.set()
                    self.stop()
                return result

            super().__init__(*args, handler=wrapped, **kwargs)

    monkeypatch.setattr(inference_main, "BatchConsumer", StoppingConsumer)
    thread = threading.Thread(target=inference_main.main)
    thread.start()
    # main() 啟動失敗時 log.catch 會吞掉例外直接結束，不必等滿逾時
    while thread.is_alive() and not done.wait(0.5):
        pass
    thread.join(TIMEOUT_S)
    assert done.is_set(), f"INFERENCE_ROLE={role.value} 的服務沒有處理到結尾事件就結束了"


def read_all(kafka_settings, topic: str) -> list[bytes]:
    reader = Consumer(consumer_config(kafka_settings, f"read-{uuid.uuid4().hex[:6]}"))
    reader.subscribe([topic])
    values: list[bytes] = []
    idle = 0
    while idle < 5:
        msg = reader.poll(1.0)
        if msg is None:
            idle += 1
        elif msg.error() is None:
            values.append(msg.value())
    reader.close()
    return values


def predictions(kafka_settings, topic: str) -> list[Prediction]:
    return [Prediction.model_validate_json(v) for v in read_all(kafka_settings, topic)]


def committed_offset(kafka_settings, group: str, topic: str) -> int:
    consumer = Consumer(consumer_config(kafka_settings, group))
    try:
        return consumer.committed([TopicPartition(topic, 0)], timeout=10)[0].offset
    finally:
        consumer.close()


def insert_row(ch, table: str, post_id: str, digest: str, mv: str) -> None:
    ch.execute(
        f"INSERT INTO {table} (post_id, model_version, predicted_at, polarity, scores, text_hash) "
        f"VALUES ('{post_id}', '{mv}', '2026-10-16 01:00:00', 'neutral', map('neutral', 1.0), "
        f"'{digest}')"
    )


# --- shadow 只寫 predictions.shadow ---


def test_shadow_role_writes_only_shadow_topic(monkeypatch, kafka_settings, env):
    producer = JsonProducer(kafka_settings)
    produce_event(producer, env.cdc, "Stock.M.1792000001.A.AAA", "c", "好棒 讚")
    producer.flush()

    run_service(monkeypatch, InferenceRole.SHADOW, kafka_settings, env)

    got = {p.post_id: p for p in predictions(kafka_settings, env.shadow_topic)}
    assert set(got) == {"Stock.M.1792000001.A.AAA", SENTINEL}
    assert {p.model_version for p in got.values()} == {env.model_version}
    assert got["Stock.M.1792000001.A.AAA"].polarity is Polarity.NEGATIVE  # FakeClassifier 的最高分
    assert predictions(kafka_settings, env.primary_topic) == []


def test_primary_role_still_writes_only_primary_topic(monkeypatch, kafka_settings, env):
    producer = JsonProducer(kafka_settings)
    produce_event(producer, env.cdc, "Stock.M.1792000002.A.BBB", "c", "好棒 讚")
    producer.flush()

    run_service(monkeypatch, InferenceRole.PRIMARY, kafka_settings, env)

    ids = {p.post_id for p in predictions(kafka_settings, env.primary_topic)}
    assert ids == {"Stock.M.1792000002.A.BBB", SENTINEL}
    assert predictions(kafka_settings, env.shadow_topic) == []


def test_shadow_role_uses_classifier_with_inference_threads(monkeypatch, kafka_settings, env):
    seen: list[int] = []
    seen_tokens: list[int] = []
    card = make_card(env.model_version)

    def load(model_dir, *, threads, max_batch_tokens):
        seen.append(threads)
        seen_tokens.append(max_batch_tokens)
        return env.classifier, card

    monkeypatch.setattr(inference_main, "load_classifier", load, raising=False)
    monkeypatch.setenv("INFERENCE_THREADS", "3")
    monkeypatch.setenv("INFERENCE_MAX_BATCH_TOKENS", "3000")

    run_service(monkeypatch, InferenceRole.SHADOW, kafka_settings, env)

    assert seen == [3]
    assert seen_tokens == [InferenceSettings().max_batch_tokens] == [3000]
    assert env.classifier.calls  # 推論走 Classifier.predict_proba


# --- consumer group ---


def test_shadow_role_commits_under_group_per_model_version(monkeypatch, kafka_settings, env):
    run_service(monkeypatch, InferenceRole.SHADOW, kafka_settings, env)

    assert committed_offset(kafka_settings, f"inference-shadow-{env.model_version}", env.cdc) >= 1
    assert committed_offset(kafka_settings, "inference", env.cdc) < 0


# --- 重啟從 predictions_shadow 載入快取 ---


def test_shadow_restart_loads_hash_cache_from_predictions_shadow_only(
    monkeypatch, kafka_settings, env, clickhouse
):
    shadow_post, primary_post = "Stock.M.1792000003.A.CCC", "Stock.M.1792000004.A.DDD"
    insert_row(clickhouse, "predictions_shadow", shadow_post, OLD_HASH, env.model_version)
    insert_row(clickhouse, "predictions", primary_post, OLD_HASH, env.model_version)
    producer = JsonProducer(kafka_settings)
    # op=u 只有快取裡有這篇、且 hash 不同才會推論
    produce_event(producer, env.cdc, shadow_post, "u", "編輯後的內文")
    produce_event(producer, env.cdc, primary_post, "u", "編輯後的內文")
    producer.flush()

    run_service(monkeypatch, InferenceRole.SHADOW, kafka_settings, env)

    got = {p.post_id: p for p in predictions(kafka_settings, env.shadow_topic)}
    assert set(got) == {shadow_post, SENTINEL}
    assert got[shadow_post].text_hash == text_hash(post_text("t", "編輯後的內文", MAX_CHARS))


def test_shadow_restart_does_not_repredict_unchanged_post(
    monkeypatch, kafka_settings, env, clickhouse
):
    post_id = "Stock.M.1792000005.A.EEE"
    digest = text_hash(post_text("t", "沒變的內文", MAX_CHARS))
    insert_row(clickhouse, "predictions_shadow", post_id, digest, env.model_version)
    producer = JsonProducer(kafka_settings)
    produce_event(producer, env.cdc, post_id, "c", "沒變的內文")
    producer.flush()

    run_service(monkeypatch, InferenceRole.SHADOW, kafka_settings, env)

    assert {p.post_id for p in predictions(kafka_settings, env.shadow_topic)} == {SENTINEL}


def test_primary_restart_still_loads_cache_from_predictions(
    monkeypatch, kafka_settings, env, clickhouse
):
    primary_post, shadow_post = "Stock.M.1792000006.A.FFF", "Stock.M.1792000007.A.GGG"
    insert_row(clickhouse, "predictions", primary_post, OLD_HASH, env.model_version)
    insert_row(clickhouse, "predictions_shadow", shadow_post, OLD_HASH, env.model_version)
    producer = JsonProducer(kafka_settings)
    produce_event(producer, env.cdc, primary_post, "u", "編輯後的內文")
    produce_event(producer, env.cdc, shadow_post, "u", "編輯後的內文")
    producer.flush()

    run_service(monkeypatch, InferenceRole.PRIMARY, kafka_settings, env)

    ids = {p.post_id for p in predictions(kafka_settings, env.primary_topic)}
    assert ids == {primary_post, SENTINEL}


# --- 冪等與 DLQ（shadow） ---


def test_shadow_duplicate_create_event_produces_one_prediction(monkeypatch, kafka_settings, env):
    producer = JsonProducer(kafka_settings)
    for _ in range(2):  # Connect 重啟後重送
        produce_event(producer, env.cdc, "Stock.M.1792000008.A.HHH", "c", "今天 下雨")
    producer.flush()

    run_service(monkeypatch, InferenceRole.SHADOW, kafka_settings, env)

    ids = [p.post_id for p in predictions(kafka_settings, env.shadow_topic)]
    assert ids.count("Stock.M.1792000008.A.HHH") == 1


def test_shadow_undecodable_message_lands_in_dlq_and_later_events_still_processed(
    monkeypatch, kafka_settings, env
):
    producer = JsonProducer(kafka_settings)
    producer._producer.produce(env.cdc, key=b"bad", value=b"not json")
    produce_event(producer, env.cdc, "Stock.M.1792000009.A.III", "c", "好棒 讚")
    producer.flush()

    run_service(monkeypatch, InferenceRole.SHADOW, kafka_settings, env)

    ids = {p.post_id for p in predictions(kafka_settings, env.shadow_topic)}
    assert "Stock.M.1792000009.A.III" in ids
    dlq = [DlqRecord.model_validate_json(v) for v in read_all(kafka_settings, DLQ_TOPIC)]
    group = f"inference-shadow-{env.model_version}"
    assert any(r.source_topic == env.cdc and r.consumer == group for r in dlq)


def test_shadow_scores_cover_all_three_classes(monkeypatch, kafka_settings, env):
    producer = JsonProducer(kafka_settings)
    produce_event(producer, env.cdc, "Stock.M.1792000010.A.JJJ", "c", "好棒 讚")
    producer.flush()

    run_service(monkeypatch, InferenceRole.SHADOW, kafka_settings, env)

    for p in predictions(kafka_settings, env.shadow_topic):
        assert set(p.scores) == set(Polarity)
        assert p.predicted_at <= datetime.now(UTC)
