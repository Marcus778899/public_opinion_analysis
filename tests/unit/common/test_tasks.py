from confluent_kafka import KafkaError, KafkaException

from radar.common.tasks import list_task_partition, resolve_list_partition

INITIAL = ["Gossiping", "Stock", "Tech_Job"]


def test_list_task_partition_initial_boards_are_distinct():
    # 重現階段 1 驗收的問題：三個看板的 key hash 都落在 partition 0（開發規格 7.10）
    partitions = {b: list_task_partition(b, INITIAL, 3) for b in INITIAL}

    assert partitions == {"Gossiping": 0, "Stock": 1, "Tech_Job": 2}


def test_list_task_partition_ignores_input_order_and_duplicates():
    shuffled = ["Tech_Job", "Stock", "Gossiping", "Stock"]

    assert [list_task_partition(b, shuffled, 3) for b in INITIAL] == [0, 1, 2]


def test_list_task_partition_more_boards_than_partitions_wraps():
    boards = ["A", "B", "C", "D"]

    assert [list_task_partition(b, boards, 3) for b in boards] == [0, 1, 2, 0]


def test_list_task_partition_unknown_board_returns_none():
    assert list_task_partition("NewBoard", INITIAL, 3) is None


def test_list_task_partition_zero_partitions_returns_none():
    assert list_task_partition("Stock", INITIAL, 0) is None


def test_resolve_list_partition_uses_partition_count():
    assert resolve_list_partition("Tech_Job", INITIAL, lambda: 3) == 2


def test_resolve_list_partition_metadata_failure_returns_none():
    def fail() -> int:
        raise KafkaException(KafkaError(KafkaError.UNKNOWN_TOPIC_OR_PART))

    assert resolve_list_partition("Stock", INITIAL, fail) is None
