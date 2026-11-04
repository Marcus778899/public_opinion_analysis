"""[常駐] 熱度偵測（S5-01～S5-04，設計文件 8.3）：消費推文 CDC，推文暴增時寫入 alerts。

以看板為 key，文章與看板兩種單位在同一份 state 計算；細節見開發規格 7.20。
純邏輯（BoardHeat 以下）不依賴 Quix，Quix 只負責消費、分組、state 與輸出。
"""

import logging
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid5

from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationError
from confluent_kafka.serialization import SerializationContext as ConfluentContext
from pydantic import ValidationError
from quixstreams import Application, State
from quixstreams.models.serializers import Deserializer, SerializationContext

from radar.common.ids import split_post_id
from radar.common.kafka.consumer import DecodeError
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log, setup_logging
from radar.common.schemas import Alert, CdcComment
from radar.common.settings import (
    HeatSettings,
    KafkaSettings,
    SchemaRegistrySettings,
    get_kafka_settings,
)

CREATE = "c"
PG_ROW_DELETED = "true"
STATE_KEY = "board_heat"
# alert_id 的 uuid5 namespace（開發規格 3.6）；固定值，改了會讓去重失效
ALERT_NAMESPACE = UUID("6f1f0b8e-6c55-4c1e-9a43-2d7f1b0c9a51")
UnitType = Literal["post", "board"]


@dataclass(frozen=True)
class HeatConfig:
    """HeatSettings 中與計算有關的部分；純邏輯只依賴這個。"""

    window_min: int = 10
    grace_min: int = 2
    max_delay_min: int = 30
    stale_after_min: int = 60
    ewma_alpha: float = 0.02
    max_gap_min: int = 1440
    z_threshold: float = 3.0
    min_count: int = 30
    post_min_count: int = 80
    cooldown_min: int = 30
    warmup_min: int = 60
    min_std: float = 1.0

    @classmethod
    def from_settings(cls, settings: HeatSettings) -> "HeatConfig":
        return cls(**{f.name: getattr(settings, f.name) for f in fields(cls)})


@dataclass
class Ewma:
    """指數加權的平均與變異數（S5-03）；samples 記錄更新次數，用來判斷是否暖機完成。"""

    mean: float = 0.0
    var: float = 0.0
    samples: int = 0

    def update(self, value: float, alpha: float) -> None:
        if self.samples == 0:
            self.mean, self.var = value, 0.0
        else:
            diff = value - self.mean
            incr = alpha * diff
            self.mean += incr
            self.var = (1 - alpha) * (self.var + diff * incr)
        self.samples += 1

    def update_pooled(self, values: list[int], alpha: float) -> None:
        """一分鐘只更新一次：以多個值的平均與平方平均更新一階、二階動差（開發規格 7.20）。"""
        if not values:
            return
        mean = sum(values) / len(values)
        sq_mean = sum(v * v for v in values) / len(values)
        if self.samples == 0:
            self.mean, self.var = mean, sq_mean - mean * mean
        else:
            # NOTE: 對二階動差做 EWMA；只有一個值時展開後與 update 相同
            second = (1 - alpha) * (self.var + self.mean**2) + alpha * sq_mean
            self.mean = (1 - alpha) * self.mean + alpha * mean
            self.var = second - self.mean**2
        self.var = max(self.var, 0.0)  # 浮點誤差可能略小於 0
        self.samples += 1

    def zscore(self, value: float, min_std: float) -> float:
        """標準差低於 min_std 時以 min_std 計算，避免變異數接近 0 時 z-score 爆大。"""
        return (value - self.mean) / max(math.sqrt(self.var), min_std)


@dataclass
class BoardHeat:
    """一個看板的 state；存進 Quix state 時轉成 dict（to_dict / from_dict）。"""

    board: str
    # 已看過最大的事件分鐘（epoch 分鐘）；None 代表還沒有任何推文
    watermark: int | None = None
    # 分鐘 → 看板推文數；只留 watermark 前 window + grace 分鐘
    board_counts: dict[int, int] = field(default_factory=dict)
    # post_id → 分鐘 → 推文數；同上，沒有推文的文章會被移除
    post_counts: dict[str, dict[int, int]] = field(default_factory=dict)
    board_baseline: Ewma = field(default_factory=Ewma)
    # 該看板活躍文章共用一個基準，每分鐘以 update_pooled 更新一次（開發規格 7.20）
    post_baseline: Ewma = field(default_factory=Ewma)
    # "post:<post_id>" / "board:<board>" → 最後一次警示的分鐘
    last_alert: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "board": self.board,
            "watermark": self.watermark,
            "board_counts": _str_keys(self.board_counts),
            "post_counts": {p: _str_keys(c) for p, c in self.post_counts.items()},
            "board_baseline": asdict(self.board_baseline),
            "post_baseline": asdict(self.post_baseline),
            "last_alert": dict(self.last_alert),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoardHeat":
        return cls(
            board=data["board"],
            watermark=data["watermark"],
            board_counts=_int_keys(data["board_counts"]),
            post_counts={p: _int_keys(c) for p, c in data["post_counts"].items()},
            board_baseline=Ewma(**data["board_baseline"]),
            post_baseline=Ewma(**data["post_baseline"]),
            last_alert=dict(data["last_alert"]),
        )


def _str_keys(counts: dict[int, int]) -> dict[str, int]:
    # NOTE: state 以 JSON 存放，dict 的 key 只能是字串
    return {str(k): v for k, v in counts.items()}


def _int_keys(counts: dict[str, int]) -> dict[int, int]:
    return {int(k): v for k, v in counts.items()}


@dataclass(frozen=True)
class Trigger:
    """觸發警示的單位；轉成 Alert 時才補上時間與 id。"""

    unit_type: UnitType
    unit_key: str
    window_end_min: int
    value: int
    baseline: float
    zscore: float
    sample_post_ids: list[str]


def event_minute(comment: CdcComment) -> int:
    """觀測時間（__source_ts_ms，推文進 PG 的時間）的 epoch 分鐘；沒有時改用 commented_at。"""
    # NOTE: 推文要等爬蟲抓到才進 PG，用推文時間會讓大部分推文超過寬限（開發規格 7.20）
    if comment.source_ts_ms is not None:
        return comment.source_ts_ms // 60_000
    if comment.commented_at is not None:
        return int(comment.commented_at.timestamp()) // 60
    raise ValueError(f"comment {comment.post_id}#{comment.floor} has no time")


def is_fresh(comment: CdcComment, max_delay_min: int) -> bool:
    """推文時間比觀測時間早不超過 max_delay_min；補抓、第一次爬到的舊爆文不計入。"""
    if comment.commented_at is None or comment.source_ts_ms is None:
        return True
    delay_s = comment.source_ts_ms / 1000 - comment.commented_at.timestamp()
    return delay_s <= max_delay_min * 60


def counts_event(comment: CdcComment) -> bool:
    """只計新增的推文（op=c）；改寫、刪除、snapshot 與 PG 端刪除的列都不算（設計文件 8.3）。"""
    return comment.op == CREATE and comment.deleted != PG_ROW_DELETED


def window_count(counts: dict[int, int], end_min: int, window_min: int) -> int:
    """(end_min - window_min, end_min] 的推文數。"""
    return sum(n for m, n in counts.items() if end_min - window_min < m <= end_min)


def advance(state: BoardHeat, minute: int, now_min: int, config: HeatConfig) -> list[Trigger]:
    """watermark 前進到 minute：逐一結算結束的分鐘（close_minute），再清掉過期的計數。"""
    if state.watermark is None:
        state.watermark = minute
        return []
    if minute <= state.watermark:
        return []
    # NOTE: 中間沒有推文的分鐘也要補 0，否則基準只看到有推文的時段而偏高
    triggers: list[Trigger] = []
    for closed in range(max(state.watermark, minute - config.max_gap_min), minute):
        triggers += close_minute(state, closed, now_min, config)
    state.watermark = minute
    keep_after = minute - config.window_min - config.grace_min
    state.board_counts = {m: n for m, n in state.board_counts.items() if m > keep_after}
    state.post_counts = {
        post_id: kept
        for post_id, counts in state.post_counts.items()
        if (kept := {m: n for m, n in counts.items() if m > keep_after})
    }
    state.last_alert = {
        unit: m for unit, m in state.last_alert.items() if minute - m < config.cooldown_min
    }
    return triggers


def close_minute(state: BoardHeat, closed: int, now_min: int, config: HeatConfig) -> list[Trigger]:
    """結算一分鐘：先以更新前的基準評估看板與所有活躍文章，再更新兩種基準。"""
    # NOTE: 不是每則推文都評估，否則一定在剛越過門檻時觸發，value 永遠停在門檻附近（#50）
    board_value = window_count(state.board_counts, closed, config.window_min)
    triggers: list[Trigger] = []
    if closed >= now_min - config.stale_after_min:
        board = evaluate(
            state, "board", state.board, closed, board_value, state.board_baseline, config
        )
        posts = (
            evaluate(state, "post", post_id, closed, value, state.post_baseline, config)
            for post_id, counts in state.post_counts.items()
            if (value := window_count(counts, closed, config.window_min)) > 0
        )
        triggers = [t for t in (board, *posts) if t is not None]
    state.board_baseline.update(board_value, config.ewma_alpha)
    state.post_baseline.update_pooled(
        post_baseline_values(state, closed, config), config.ewma_alpha
    )
    return triggers


def post_baseline_values(state: BoardHeat, closed: int, config: HeatConfig) -> list[int]:
    """更新文章基準用的視窗值：視窗內有推文、且不在冷卻中的文章（冷卻包含剛觸發的）。"""
    values = (
        window_count(counts, closed, config.window_min)
        for post_id, counts in state.post_counts.items()
        if f"post:{post_id}" not in state.last_alert
    )
    return [v for v in values if v > 0]


def record(
    state: BoardHeat, comment: CdcComment, now_min: int, config: HeatConfig
) -> list[Trigger]:
    """處理一則推文：太舊或寬限外的丟棄；計數後推進 watermark，回傳結算分鐘產生的 Trigger。"""
    if not is_fresh(comment, config.max_delay_min):
        return []
    minute = event_minute(comment)
    if state.watermark is not None and minute < state.watermark - config.grace_min:
        return []
    state.board_counts[minute] = state.board_counts.get(minute, 0) + 1
    post = state.post_counts.setdefault(comment.post_id, {})
    post[minute] = post.get(minute, 0) + 1
    return advance(state, minute, now_min, config)


def min_count_for(unit_type: UnitType, config: HeatConfig) -> int:
    """觸發所需的最低推文數：文章用 post_min_count，看板用 min_count。"""
    return config.post_min_count if unit_type == "post" else config.min_count


def evaluate(
    state: BoardHeat,
    unit_type: UnitType,
    unit_key: str,
    end_min: int,
    value: int,
    baseline: Ewma,
    config: HeatConfig,
) -> Trigger | None:
    """單一單位在結算分鐘 end_min 是否觸發；觸發時記錄 last_alert（冷卻）。"""
    if state.board_baseline.samples < config.warmup_min:
        return None
    if value < min_count_for(unit_type, config):
        return None
    z = baseline.zscore(value, config.min_std)
    if z < config.z_threshold:
        return None
    unit = f"{unit_type}:{unit_key}"
    last = state.last_alert.get(unit)
    if last is not None and end_min - last < config.cooldown_min:
        return None
    state.last_alert[unit] = end_min
    samples = [unit_key] if unit_type == "post" else top_posts(state, end_min, config.window_min)
    return Trigger(unit_type, unit_key, end_min, value, baseline.mean, z, samples)


def top_posts(state: BoardHeat, end_min: int, window_min: int, limit: int = 3) -> list[str]:
    """視窗內推文最多的文章，當作看板警示的 sample_post_ids（開發規格 3.6）。"""
    counts = {
        post_id: window_count(c, end_min, window_min) for post_id, c in state.post_counts.items()
    }
    ranked = sorted((p for p, n in counts.items() if n > 0), key=lambda p: (-counts[p], p))
    return ranked[:limit]


def minute_end(minute: int) -> datetime:
    """分鐘 m 代表 [m, m+1)，視窗結束時間是下一分鐘的開頭。"""
    return datetime.fromtimestamp((minute + 1) * 60, UTC)


def alert_id(unit_type: UnitType, unit_key: str, window_end: datetime) -> UUID:
    """uuid5(unit_type, unit_key, window_end)；同一個警示重送時 id 相同（開發規格 3.6）。"""
    return uuid5(ALERT_NAMESPACE, f"{unit_type}|{unit_key}|{window_end.isoformat()}")


def to_alert(trigger: Trigger, board: str, config: HeatConfig, created_at: datetime) -> Alert:
    window_end = minute_end(trigger.window_end_min)
    return Alert(
        alert_id=alert_id(trigger.unit_type, trigger.unit_key, window_end),
        unit_type=trigger.unit_type,
        unit_key=trigger.unit_key,
        board=board,
        window_start=window_end - timedelta(minutes=config.window_min),
        window_end=window_end,
        value=trigger.value,
        baseline=round(trigger.baseline, 3),
        zscore=round(trigger.zscore, 3),
        sample_post_ids=trigger.sample_post_ids,
        created_at=created_at,
    )


class CdcCommentDeserializer(Deserializer):
    """Apicurio 序列化的 Avro → CdcComment 的 dict（含 __op 等別名）；Quix 的 deserializer。"""

    def __init__(self, registry: SchemaRegistryClient) -> None:
        super().__init__()
        self._avro = AvroDeserializer(registry)

    def __call__(self, value: bytes, ctx: SerializationContext) -> dict[str, Any]:
        try:
            record = self._avro(value, ConfluentContext(ctx.topic, MessageField.VALUE))
            if record is None:
                raise DecodeError("tombstone or empty message")
            comment = CdcComment.model_validate(record)
        except (SerializationError, ValidationError) as e:
            raise DecodeError(f"cdc comment decode failed: {e}") from e
        return comment.model_dump(mode="json", by_alias=True)


# NOTE: Quix 的 callback 簽名帶標準 logging.Logger；只用在型別，log 仍用 radar.common.log
ConsumerErrorCallback = Callable[[Exception, Any, logging.Logger], bool]


def is_decode_error(exc: BaseException) -> bool:
    """Quix 可能把 deserializer 的例外再包一層；沿著 __cause__ 找 DecodeError。"""
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, DecodeError):
            return True
        current = current.__cause__
    return False


def make_on_consumer_error(dlq: DlqPublisher) -> ConsumerErrorCallback:
    """Quix 的 on_consumer_error：解析失敗的訊息送 dlq 並略過；其他錯誤不吞（服務停止）。"""

    def on_error(exc: Exception, message: Any, _logger: logging.Logger) -> bool:
        if message is None or not is_decode_error(exc):
            return False
        log.warning("comment decode failed, sent to dlq: %s", exc)
        dlq.publish(message, exc)
        return True

    return on_error


def board_of(value: dict[str, Any]) -> str:
    board, _ = split_post_id(str(value["post_id"]))
    return board


def counts_value(value: dict[str, Any]) -> bool:
    return counts_event(CdcComment.model_validate(value))


def process(
    value: dict[str, Any], state: State, config: HeatConfig, now: datetime
) -> list[dict[str, Any]]:
    """Quix 的 stateful apply：讀出 BoardHeat、record、寫回，回傳要送出的 Alert（JSON dict）。"""
    comment = CdcComment.model_validate(value)
    board = board_of(value)
    stored = state.get(STATE_KEY)
    heat = BoardHeat.from_dict(stored) if stored is not None else BoardHeat(board)
    triggers = record(heat, comment, int(now.timestamp()) // 60, config)
    state.set(STATE_KEY, heat.to_dict())
    return [to_alert(t, board, config, now).model_dump(mode="json") for t in triggers]


def build_app(
    settings: HeatSettings,
    kafka: KafkaSettings,
    dlq: DlqPublisher,
    registry: SchemaRegistryClient,
) -> Application:
    """Application、輸入 topic、group_by(board)、stateful apply、輸出到 alerts。"""
    config = HeatConfig.from_settings(settings)
    app = Application(
        broker_address=kafka.bootstrap_servers,
        consumer_group=settings.consumer_group,
        # NOTE: 新的 consumer group 從頭讀：歷史推文都是舊推文，只用來建立基準，不會觸發
        auto_offset_reset="earliest",
        processing_guarantee="exactly-once",
        state_dir=settings.state_dir,
        on_consumer_error=make_on_consumer_error(dlq),
        loglevel="WARNING",
    )
    comments = app.topic(
        settings.input_topic,
        value_deserializer=CdcCommentDeserializer(registry),
        key_deserializer="bytes",
    )
    alerts = app.topic(settings.output_topic, value_serializer="json", key_serializer="str")
    sdf = app.dataframe(comments)
    sdf = sdf.filter(counts_value)
    sdf = sdf.group_by(board_of, name="board")
    sdf = sdf.apply(
        lambda value, state: process(value, state, config, datetime.now(UTC)),
        stateful=True,
        expand=True,
    )
    sdf.to_topic(alerts, key=lambda alert: alert["unit_key"])
    return app


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("heat")
    settings = HeatSettings()
    kafka = get_kafka_settings()
    producer = JsonProducer(kafka)
    registry = SchemaRegistryClient.new_client({"url": SchemaRegistrySettings().url})
    app = build_app(settings, kafka, DlqPublisher(producer, settings.consumer_group), registry)
    log.info("heat consuming %s as %s", settings.input_topic, settings.consumer_group)
    try:
        app.run()
    finally:
        producer.flush()


if __name__ == "__main__":
    main()
