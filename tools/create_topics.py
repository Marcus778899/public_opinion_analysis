"""依 infra/kafka/topics.yaml 建立或更新 topic（冪等）。用法：make topics"""

from pathlib import Path

from confluent_kafka.admin import AdminClient

from radar.common.kafka.config import admin_config
from radar.common.kafka.topics import apply_plan, fetch_existing, load_topic_specs, plan_changes
from radar.common.log import log, setup_logging
from radar.common.settings import get_kafka_settings

TOPICS_FILE = Path(__file__).resolve().parents[1] / "infra/kafka/topics.yaml"


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("create-topics")
    specs = load_topic_specs(TOPICS_FILE)
    admin = AdminClient(admin_config(get_kafka_settings()))
    plan = plan_changes(specs, fetch_existing(admin, [s.name for s in specs]))
    if plan.is_empty():
        log.info("all %d topics up to date", len(specs))
        return
    for spec in plan.create:
        log.info("create %s (partitions=%d)", spec.name, spec.partitions)
    for name, count in plan.add_partitions.items():
        log.info("add partitions %s -> %d", name, count)
    for name, config in plan.alter_config.items():
        log.info("alter config %s %s", name, config)
    apply_plan(admin, plan)
    log.info("done")


if __name__ == "__main__":
    main()
