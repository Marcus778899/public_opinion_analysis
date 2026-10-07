from pathlib import Path

from radar.common.kafka import names
from radar.common.kafka.topics import load_topic_specs

REPO_TOPICS = Path(__file__).resolve().parents[4] / "infra/kafka/topics.yaml"


def test_topic_names_match_topics_yaml():
    constants = {v for k, v in vars(names).items() if k.isupper()}

    assert constants == {s.name for s in load_topic_specs(REPO_TOPICS)}
