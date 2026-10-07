from pathlib import Path

import pytest
from confluent_kafka import KafkaError, KafkaException

from radar.common.kafka.topics import (
    ExistingTopic,
    TopicPlan,
    TopicSpec,
    apply_plan,
    fetch_existing,
    load_topic_specs,
    plan_changes,
)

REPO_TOPICS = Path(__file__).resolve().parents[4] / "infra/kafka/topics.yaml"

YAML = """
defaults:
  replication_factor: 3
  config:
    compression.type: zstd
topics:
  - name: a
    partitions: 3
    retention_hours: 24
  - name: b
    partitions: 1
    replication_factor: 1
    config:
      compression.type: lz4
      max.message.bytes: 5242880
"""


@pytest.fixture
def topics_file(tmp_path):
    path = tmp_path / "topics.yaml"
    path.write_text(YAML)
    return path


def spec(name="a", partitions=3, **config):
    return TopicSpec(name, partitions, 3, {k.replace("_", "."): v for k, v in config.items()})


def existing(name="a", partitions=3, **config):
    return ExistingTopic(name, partitions, {k.replace("_", "."): v for k, v in config.items()})


def test_load_topic_specs_merges_defaults(topics_file):
    a, b = load_topic_specs(topics_file)

    assert a.replication_factor == 3
    assert a.config["compression.type"] == "zstd"
    assert b.replication_factor == 1
    assert b.config["compression.type"] == "lz4"


def test_load_topic_specs_converts_retention_hours_to_ms(topics_file):
    a, _ = load_topic_specs(topics_file)

    assert a.config["retention.ms"] == str(24 * 3600 * 1000)


def test_load_topic_specs_stringifies_config_values(topics_file):
    _, b = load_topic_specs(topics_file)

    assert b.config["max.message.bytes"] == "5242880"


def test_load_topic_specs_rejects_duplicate_names(tmp_path):
    path = tmp_path / "t.yaml"
    path.write_text("topics:\n  - {name: a, partitions: 1}\n  - {name: a, partitions: 1}\n")

    with pytest.raises(ValueError, match="duplicate"):
        load_topic_specs(path)


def test_plan_creates_missing_topics():
    plan = plan_changes([spec("a"), spec("b")], {"a": existing("a")})

    assert [s.name for s in plan.create] == ["b"]


def test_plan_is_empty_when_everything_matches():
    plan = plan_changes([spec(retention_ms="1")], {"a": existing(retention_ms="1", other="x")})

    assert plan.is_empty()


def test_plan_alters_only_changed_config():
    desired = spec(retention_ms="2", compression_type="zstd")

    plan = plan_changes([desired], {"a": existing(retention_ms="1", compression_type="zstd")})

    assert plan.alter_config == {"a": {"retention.ms": "2"}}


def test_plan_adds_partitions_when_desired_is_larger():
    plan = plan_changes([spec(partitions=6)], {"a": existing(partitions=3)})

    assert plan.add_partitions == {"a": 6}


def test_plan_raises_when_desired_partitions_is_smaller():
    with pytest.raises(ValueError, match="shrink"):
        plan_changes([spec(partitions=1)], {"a": existing(partitions=3)})


def test_plan_ignores_topics_not_in_yaml():
    plan = plan_changes([spec("a")], {"a": existing("a"), "legacy": existing("legacy")})

    assert plan.is_empty()


def test_repo_topics_yaml_is_valid():
    specs = load_topic_specs(REPO_TOPICS)

    names = {s.name for s in specs}
    assert {"crawl.tasks", "raw.posts", "raw.html", "dlq", "alerts"} <= names
    assert all(s.replication_factor == 3 for s in specs)
    raw_html = next(s for s in specs if s.name == "raw.html")
    assert raw_html.config["max.message.bytes"] == "5242880"


class FakeFuture:
    def __init__(self, result=None, error: Exception | None = None):
        self._result = result
        self._error = error

    def result(self):
        if self._error:
            raise self._error
        return self._result


class FakeAdmin:
    def __init__(self, topics=None, create_error: Exception | None = None):
        self.topics = topics or {}
        self.create_error = create_error
        self.calls: dict[str, list] = {}

    def list_topics(self, timeout):
        meta = type("Meta", (), {})()
        meta.topics = {
            name: type("T", (), {"partitions": dict.fromkeys(range(p))})()
            for name, (p, _) in self.topics.items()
        }
        return meta

    def describe_configs(self, resources):
        entry = lambda v: type("E", (), {"value": v})()  # noqa: E731
        return {
            r: FakeFuture({k: entry(v) for k, v in self.topics[r.name][1].items()})
            for r in resources
        }

    def create_topics(self, new_topics):
        self.calls["create"] = new_topics
        return {t.topic: FakeFuture(error=self.create_error) for t in new_topics}

    def create_partitions(self, new_partitions):
        self.calls["partitions"] = new_partitions
        return {p.topic: FakeFuture() for p in new_partitions}

    def incremental_alter_configs(self, resources):
        self.calls["alter"] = resources
        return {r: FakeFuture() for r in resources}


def test_fetch_existing_returns_only_present_topics():
    admin = FakeAdmin({"a": (3, {"retention.ms": "1", "x": None})})

    result = fetch_existing(admin, ["a", "missing"])

    assert result == {"a": ExistingTopic("a", 3, {"retention.ms": "1"})}


def test_fetch_existing_with_no_present_topics_skips_describe():
    assert fetch_existing(FakeAdmin(), ["missing"]) == {}


def test_apply_plan_calls_admin_for_each_change_type():
    admin = FakeAdmin()
    plan = TopicPlan(
        create=[spec("new")], add_partitions={"a": 6}, alter_config={"a": {"retention.ms": "2"}}
    )

    apply_plan(admin, plan)

    assert [t.topic for t in admin.calls["create"]] == ["new"]
    assert [p.topic for p in admin.calls["partitions"]] == ["a"]
    assert [r.name for r in admin.calls["alter"]] == ["a"]


def test_apply_plan_empty_makes_no_calls():
    admin = FakeAdmin()

    apply_plan(admin, TopicPlan())

    assert admin.calls == {}


def test_apply_plan_ignores_topic_already_exists():
    exists = KafkaException(KafkaError(KafkaError.TOPIC_ALREADY_EXISTS))

    apply_plan(FakeAdmin(create_error=exists), TopicPlan(create=[spec("a")]))


def test_apply_plan_raises_other_create_errors():
    denied = KafkaException(KafkaError(KafkaError.TOPIC_AUTHORIZATION_FAILED))

    with pytest.raises(KafkaException):
        apply_plan(FakeAdmin(create_error=denied), TopicPlan(create=[spec("a")]))
