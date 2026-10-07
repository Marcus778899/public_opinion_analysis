import importlib

import pytest

PACKAGES = [
    "radar.common",
    "radar.common.db.models",
    "radar.common.db.session",
    "radar.common.enums",
    "radar.common.ids",
    "radar.common.schemas",
    "radar.common.kafka.consumer",
    "radar.common.kafka.topics",
    "radar.common.log",
    "radar.common.retry",
    "radar.common.settings",
    "radar.api",
    "radar.collector",
    "radar.collector.parsers",
    "radar.collector.parsers.ptt",
    "radar.collector.parsers.ptt_time",
    "radar.collector.crawler",
    "radar.collector.http",
    "radar.collector.list_cache",
    "radar.collector.recrawl",
    "radar.collector.scheduler",
    "radar.collector.rate_limit",
    "radar.ingest.main",
    "radar.ingest.writer",
    "radar.api.deps",
    "radar.api.kafka_ops",
    "radar.api.repository",
    "radar.api.routes.boards",
    "radar.api.routes.status",
    "radar.api.schemas",
    "radar.api.seed",
    "radar.ingest",
    "radar.ml.labeling",
    "radar.ml.training",
    "radar.ml.inference",
    "radar.streaming",
    "radar.bot",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_importable(name):
    importlib.import_module(name)
