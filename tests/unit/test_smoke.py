import importlib

import pytest

PACKAGES = [
    "radar.common",
    "radar.common.db.models",
    "radar.api",
    "radar.collector",
    "radar.collector.parsers",
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
