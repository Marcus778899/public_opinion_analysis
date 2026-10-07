from dataclasses import dataclass, field
from pathlib import Path

import yaml
from confluent_kafka import KafkaError, KafkaException
from confluent_kafka.admin import (
    AdminClient,
    AlterConfigOpType,
    ConfigEntry,
    ConfigResource,
    NewPartitions,
    NewTopic,
    ResourceType,
)

_MS_PER_HOUR = 3600 * 1000


@dataclass(frozen=True)
class TopicSpec:
    name: str
    partitions: int
    replication_factor: int
    config: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExistingTopic:
    name: str
    partitions: int
    config: dict[str, str]


@dataclass
class TopicPlan:
    create: list[TopicSpec] = field(default_factory=list)
    alter_config: dict[str, dict[str, str]] = field(default_factory=dict)
    add_partitions: dict[str, int] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.create or self.alter_config or self.add_partitions)


def load_topic_specs(path: Path) -> list[TopicSpec]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    specs: list[TopicSpec] = []
    for topic in raw["topics"]:
        config = {**defaults.get("config", {}), **topic.get("config", {})}
        if "retention_hours" in topic:
            config["retention.ms"] = int(topic["retention_hours"]) * _MS_PER_HOUR
        specs.append(
            TopicSpec(
                name=topic["name"],
                partitions=int(topic["partitions"]),
                replication_factor=int(
                    topic.get("replication_factor", defaults.get("replication_factor", 1))
                ),
                config={k: str(v) for k, v in config.items()},
            )
        )
    names = [s.name for s in specs]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ValueError(f"duplicate topics in {path}: {sorted(duplicates)}")
    return specs


def plan_changes(desired: list[TopicSpec], existing: dict[str, ExistingTopic]) -> TopicPlan:
    """純函式，方便單元測試；不刪除 yaml 沒列的 topic。"""
    # NOTE: replication factor 變更需要重新分配 partition，不在此處理
    plan = TopicPlan()
    for spec in desired:
        current = existing.get(spec.name)
        if current is None:
            plan.create.append(spec)
            continue
        if spec.partitions < current.partitions:
            raise ValueError(
                f"{spec.name}: partitions cannot shrink ({current.partitions} -> {spec.partitions})"
            )
        if spec.partitions > current.partitions:
            plan.add_partitions[spec.name] = spec.partitions
        changed = {k: v for k, v in spec.config.items() if current.config.get(k) != v}
        if changed:
            plan.alter_config[spec.name] = changed
    return plan


def fetch_existing(admin: AdminClient, names: list[str]) -> dict[str, ExistingTopic]:
    metadata = admin.list_topics(timeout=10)
    present = [n for n in names if n in metadata.topics]
    if not present:
        return {}
    futures = admin.describe_configs([ConfigResource(ResourceType.TOPIC, n) for n in present])
    existing: dict[str, ExistingTopic] = {}
    for resource, future in futures.items():
        entries = future.result()
        existing[resource.name] = ExistingTopic(
            name=resource.name,
            partitions=len(metadata.topics[resource.name].partitions),
            config={k: e.value for k, e in entries.items() if e.value is not None},
        )
    return existing


def apply_plan(admin: AdminClient, plan: TopicPlan) -> None:
    if plan.create:
        new_topics = [
            NewTopic(s.name, s.partitions, s.replication_factor, config=s.config)
            for s in plan.create
        ]
        for future in admin.create_topics(new_topics).values():
            try:
                future.result()
            except KafkaException as e:
                # NOTE: metadata 尚未同步時 fetch_existing 會漏看剛建立的 topic，視為已存在
                if e.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                    raise
    if plan.add_partitions:
        new_partitions = [NewPartitions(n, c) for n, c in plan.add_partitions.items()]
        for future in admin.create_partitions(new_partitions).values():
            future.result()
    if plan.alter_config:
        resources = [
            ConfigResource(
                ResourceType.TOPIC,
                name,
                incremental_configs=[
                    ConfigEntry(k, v, incremental_operation=AlterConfigOpType.SET)
                    for k, v in config.items()
                ],
            )
            for name, config in plan.alter_config.items()
        ]
        for future in admin.incremental_alter_configs(resources).values():
            future.result()
