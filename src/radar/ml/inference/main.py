"""[常駐] 情緒推論（S4-01～S4-03，設計文件 8.2）：消費 cdc.public.posts，推論後寫入角色的 topic。

是否推論只看模型輸入文字的 hash，大部分只更新推噓數的事件不會重複推論（開發規格 7.18）；
啟動時從 ClickHouse 載入 hash，重啟後被編輯的文章照常推論（開發規格 7.19）。
"""

import hashlib
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from confluent_kafka.schema_registry import SchemaRegistryClient

from radar.common.clickhouse import ClickHouseClient
from radar.common.enums import Polarity
from radar.common.kafka import names
from radar.common.kafka.avro import make_avro_decoder
from radar.common.kafka.consumer import BatchConsumer
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log, setup_logging
from radar.common.schemas import CdcPost, Prediction
from radar.common.settings import (
    ClickHouseSettings,
    InferenceSettings,
    SchemaRegistrySettings,
    get_kafka_settings,
)
from radar.ml.inference.roles import ROLE_TARGETS, consumer_group
from radar.ml.training.classifier import Classifier, load_classifier
from radar.ml.training.dataset import post_text
from radar.ml.training.train import ModelCard

CREATE = "c"
# PG 端刪除列時 __deleted 為 "true"（設計文件 6.1）
PG_ROW_DELETED = "true"
# 每篇取最新一筆；依 predicted_at 由舊到新回傳，放進 LRU 後最新的最不會被擠出
# NOTE: 別名不可與欄位同名，否則 WHERE 的 text_hash 會指到 argMax(...)
CACHE_QUERY = """
SELECT post_id, argMax(text_hash, predicted_at) AS latest_hash, max(predicted_at) AS latest_at
FROM {table}
WHERE model_version = {model_version:String} AND text_hash != ''
GROUP BY post_id
ORDER BY latest_at
"""


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class HashCache:
    """post_id → 最後一次看到的模型輸入文字 hash；LRU，超過上限丟最久沒用的。"""

    def __init__(self, max_size: int) -> None:
        self._max_size = max_size
        self._data: OrderedDict[str, str] = OrderedDict()

    def get(self, post_id: str) -> str | None:
        digest = self._data.get(post_id)
        if digest is not None:
            self._data.move_to_end(post_id)
        return digest

    def put(self, post_id: str, digest: str) -> None:
        self._data[post_id] = digest
        self._data.move_to_end(post_id)
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


def load_cache(
    client: ClickHouseClient, model_version: str, cache: HashCache, table: str = "predictions"
) -> int:
    """把同一個模型版本每篇最新推論的 text_hash 放進快取；回傳載入的篇數。"""
    # NOTE: ClickHouse 的錯誤直接往上拋：服務停止、由 docker 重啟，不以空快取開始消費
    # NOTE: 表名只接受 roles 對照表裡的值，避免拼進 SQL 的字串來自外部
    if table not in {t.table for t in ROLE_TARGETS.values()}:
        raise ValueError(f"unknown inference table: {table}")
    sql = CACHE_QUERY.replace("{table}", table)
    rows = client.query_rows(sql, {"model_version": model_version})
    for row in rows:
        cache.put(str(row["post_id"]), str(row["latest_hash"]))
    return len(rows)


def should_predict(op: str | None, cached: str | None, digest: str) -> bool:
    """快取有這篇 → hash 不同才推論；快取沒有 → 只有新文章（op=c）推論。"""
    # NOTE: 重啟後快取是空的，對 op=u 也推論的話，每篇的第一次推噓數變化都會重複推論
    if cached is not None:
        return cached != digest
    return op == CREATE


@dataclass(frozen=True)
class PendingPost:
    post_id: str
    text: str
    digest: str


@dataclass(frozen=True)
class Selection:
    to_predict: list[PendingPost]
    # 這批看到的所有未刪除文章的 hash（含不需推論的）；flush 成功後才寫入快取
    seen: dict[str, str]


def select_posts(events: list[CdcPost], cache: HashCache, max_chars: int) -> Selection:
    """同一篇有多筆事件時只看最後一筆；is_deleted 或 __deleted 的跳過，也不記 hash。"""
    latest: dict[str, CdcPost] = {}
    created: set[str] = set()
    for event in events:
        latest.pop(event.post_id, None)
        latest[event.post_id] = event
        if event.op == CREATE:
            # NOTE: 同一批裡新文章後面接著推噓數更新時，最後一筆是 u，仍要當成新文章推論
            created.add(event.post_id)
    to_predict: list[PendingPost] = []
    seen: dict[str, str] = {}
    for post_id, event in latest.items():
        if event.is_deleted or event.deleted == PG_ROW_DELETED:
            continue
        text = post_text(event.title, event.content, max_chars)
        digest = text_hash(text)
        seen[post_id] = digest
        op = CREATE if post_id in created else event.op
        if should_predict(op, cache.get(post_id), digest):
            to_predict.append(PendingPost(post_id, text, digest))
    return Selection(to_predict, seen)


def top_class(scores: dict[Polarity, float]) -> Polarity:
    """最高分的類別；同分時取 Polarity 宣告順序的第一個。"""
    return max(Polarity, key=lambda c: scores.get(c, 0.0))


class Predictor:
    """BatchConsumer 的 handler：選文章 → 批次推論 → 送出並 flush → 更新快取。"""

    def __init__(
        self,
        classifier: Classifier,
        card: ModelCard,
        cache: HashCache,
        publish: Callable[[Prediction], None],
        flush: Callable[[], None],
        now: Callable[[], datetime],
    ) -> None:
        self._classifier = classifier
        self._card = card
        self._cache = cache
        self._publish = publish
        self._flush = flush
        self._now = now

    def __call__(self, events: list[CdcPost]) -> None:
        selection = select_posts(events, self._cache, self._card.max_chars)
        pending = selection.to_predict
        if pending:
            results = self._classifier.predict_proba([p.text for p in pending])
            predicted_at = self._now()
            for post, scores in zip(pending, results, strict=True):
                self._publish(
                    Prediction(
                        post_id=post.post_id,
                        model_version=self._card.model_version,
                        predicted_at=predicted_at,
                        polarity=top_class(scores),
                        scores=scores,
                        text_hash=post.digest,
                    )
                )
            # NOTE: flush 成功後才更新快取；整批重試時不會把沒送出的文章當成已推論
            self._flush()
        for post_id, digest in selection.seen.items():
            self._cache.put(post_id, digest)


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("inference")
    settings = InferenceSettings()
    targets = ROLE_TARGETS[settings.role]
    classifier, card = load_classifier(settings.model_dir, threads=settings.threads)
    group_id = consumer_group(settings.role, card.model_version)
    cache = HashCache(settings.cache_size)
    ch = ClickHouseClient(ClickHouseSettings())
    try:
        loaded = load_cache(ch, card.model_version, cache, targets.table)
    finally:
        ch.close()
    log.info("loaded %d post hashes from clickhouse", loaded)
    producer = JsonProducer(get_kafka_settings())
    registry = SchemaRegistryClient.new_client({"url": SchemaRegistrySettings().url})
    handler = Predictor(
        classifier,
        card,
        cache,
        publish=lambda p: producer.send(targets.topic, p.post_id, p),
        flush=producer.flush,
        now=lambda: datetime.now(UTC),
    )
    consumer = BatchConsumer(
        get_kafka_settings(),
        group_id=group_id,
        topics=[names.CDC_POSTS],
        model=CdcPost,
        handler=handler,
        dlq=DlqPublisher(producer, group_id),
        batch_size=settings.batch_size,
        decode=make_avro_decoder(CdcPost, registry),
    )
    log.info(
        "inference %s with %s (trained on %s)",
        settings.role.value,
        card.model_version,
        card.label_version,
    )
    try:
        consumer.run()
    finally:
        producer.flush()


if __name__ == "__main__":
    main()
