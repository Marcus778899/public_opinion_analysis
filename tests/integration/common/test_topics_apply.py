import dataclasses
import time
import uuid
from pathlib import Path

from confluent_kafka.admin import AdminClient

from radar.common.kafka.config import admin_config
from radar.common.kafka.topics import (
    apply_plan,
    fetch_existing,
    load_topic_specs,
    plan_changes,
)

REPO_TOPICS = Path(__file__).resolve().parents[3] / "infra/kafka/topics.yaml"


def single_node_specs(prefix: str):
    # NOTE: 測試用單節點，副本數改成 1；名稱加前綴避免測試間互相影響
    specs = load_topic_specs(REPO_TOPICS)
    return [
        dataclasses.replace(
            s,
            name=f"{prefix}.{s.name}",
            replication_factor=1,
            config={**s.config, "min.insync.replicas": "1"},
        )
        for s in specs
    ]


def wait_visible(admin, names, timeout_s=10.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if set(fetch_existing(admin, names)) == set(names):
            return
        time.sleep(0.2)
    raise AssertionError(f"topics not visible: {names}")


def test_apply_creates_all_topics_from_yaml(kafka_settings):
    admin = AdminClient(admin_config(kafka_settings))
    specs = single_node_specs(uuid.uuid4().hex[:8])

    apply_plan(admin, plan_changes(specs, fetch_existing(admin, [s.name for s in specs])))
    wait_visible(admin, [s.name for s in specs])

    existing = fetch_existing(admin, [s.name for s in specs])
    assert set(existing) == {s.name for s in specs}
    raw_html = next(v for k, v in existing.items() if k.endswith(".raw.html"))
    assert raw_html.config["max.message.bytes"] == "5242880"
    assert raw_html.config["retention.ms"] == str(72 * 3600 * 1000)


def test_apply_twice_is_noop(kafka_settings):
    admin = AdminClient(admin_config(kafka_settings))
    specs = single_node_specs(uuid.uuid4().hex[:8])
    names = [s.name for s in specs]
    apply_plan(admin, plan_changes(specs, fetch_existing(admin, names)))
    wait_visible(admin, names)

    assert plan_changes(specs, fetch_existing(admin, names)).is_empty()


def test_apply_tolerates_topic_created_but_not_yet_visible(kafka_settings):
    admin = AdminClient(admin_config(kafka_settings))
    spec = single_node_specs(uuid.uuid4().hex[:8])[0]
    apply_plan(admin, plan_changes([spec], {}))

    apply_plan(admin, plan_changes([spec], {}))


def test_apply_updates_changed_retention_and_partitions(kafka_settings):
    admin = AdminClient(admin_config(kafka_settings))
    spec = single_node_specs(uuid.uuid4().hex[:8])[0]
    apply_plan(admin, plan_changes([spec], {}))
    wait_visible(admin, [spec.name])
    changed = dataclasses.replace(
        spec, partitions=spec.partitions + 1, config={**spec.config, "retention.ms": "3600000"}
    )

    apply_plan(admin, plan_changes([changed], fetch_existing(admin, [spec.name])))

    current = fetch_existing(admin, [spec.name])[spec.name]
    assert current.partitions == spec.partitions + 1
    assert current.config["retention.ms"] == "3600000"
