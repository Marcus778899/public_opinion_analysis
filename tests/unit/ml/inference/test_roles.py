import pytest

from radar.common.kafka import names
from radar.common.settings import InferenceRole
from radar.ml.inference.roles import ROLE_TARGETS, consumer_group


def test_primary_role_keeps_existing_group_topic_and_table():
    targets = ROLE_TARGETS[InferenceRole.PRIMARY]

    assert consumer_group(InferenceRole.PRIMARY, "bert-x") == "inference"
    assert (targets.topic, targets.table) == (names.PREDICTIONS, "predictions")


def test_shadow_role_writes_shadow_topic_and_table():
    targets = ROLE_TARGETS[InferenceRole.SHADOW]

    assert (targets.topic, targets.table) == (names.PREDICTIONS_SHADOW, "predictions_shadow")


@pytest.mark.parametrize("version", ["bert-macbert-202610210000", "bert-ckip-202610210000-int8"])
def test_shadow_group_differs_per_model_version(version):
    assert consumer_group(InferenceRole.SHADOW, version) == f"inference-shadow-{version}"


def test_every_role_has_targets():
    assert set(ROLE_TARGETS) == set(InferenceRole)
