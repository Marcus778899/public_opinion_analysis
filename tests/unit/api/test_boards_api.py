import json

from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.kafka import names
from radar.common.schemas import CrawlTask


def test_list_boards_returns_all_sorted(client, repo):
    repo.add("Tech_Job")
    repo.add("Gossiping")

    response = client.get("/boards")

    assert response.status_code == 200
    assert [b["board"] for b in response.json()] == ["Gossiping", "Tech_Job"]


def test_create_board_returns_201(client):
    response = client.post("/boards", json={"board": "Stock", "interval_sec": 120})

    assert response.status_code == 201
    body = response.json()
    assert (body["board"], body["interval_sec"], body["enabled"]) == ("Stock", 120, True)


def test_create_duplicate_board_returns_409(client, repo):
    repo.add("Stock")

    response = client.post("/boards", json={"board": "Stock", "interval_sec": 120})

    assert response.status_code == 409


def test_create_board_invalid_interval_returns_422(client):
    response = client.post("/boards", json={"board": "Stock", "interval_sec": 10})

    assert response.status_code == 422


def test_update_board_partial_fields(client, repo):
    repo.add("Stock", interval_sec=120)

    response = client.patch("/boards/Stock", json={"enabled": False})

    assert response.status_code == 200
    assert (response.json()["enabled"], response.json()["interval_sec"]) == (False, 120)


def test_update_board_empty_body_returns_422(client, repo):
    repo.add("Stock")

    assert client.patch("/boards/Stock", json={}).status_code == 422


def test_update_unknown_board_returns_404(client):
    assert client.patch("/boards/Nope", json={"enabled": False}).status_code == 404


def test_trigger_crawl_sends_manual_list_task_keyed_by_board(client, repo, fake_producer):
    repo.add("Stock")

    response = client.post("/boards/Stock/crawl")

    assert response.status_code == 202
    sent = fake_producer.produced[0]
    assert (sent["topic"], sent["key"]) == (names.CRAWL_TASKS, b"Stock")
    task = CrawlTask.model_validate(json.loads(sent["value"]))
    assert (task.type, task.reason) == (CrawlTaskType.LIST, CrawlReason.MANUAL)
    assert task.url == "https://www.ptt.cc/bbs/Stock/index.html"
    assert response.json()["task_id"] == str(task.task_id)


def test_trigger_crawl_allowed_for_disabled_board(client, repo):
    repo.add("Stock", enabled=False)

    assert client.post("/boards/Stock/crawl").status_code == 202


def test_trigger_crawl_unknown_board_returns_404(client, fake_producer):
    assert client.post("/boards/Nope/crawl").status_code == 404
    assert fake_producer.produced == []


def test_trigger_crawl_kafka_failure_returns_503(client, repo, fake_producer):
    repo.add("Stock")
    fake_producer.fail_delivery = True

    assert client.post("/boards/Stock/crawl").status_code == 503


def test_trigger_crawl_sets_partition_from_enabled_boards(client, repo, fake_producer):
    fake_producer.topic_partitions = {names.CRAWL_TASKS: 3}
    for name in ["Gossiping", "Stock", "Tech_Job"]:
        repo.add(name)
    repo.add("Aaa", enabled=False)  # 停用的看板不參與排序

    client.post("/boards/Stock/crawl")

    assert fake_producer.produced[0]["partition"] == 1


def test_trigger_crawl_metadata_failure_falls_back_to_key_hash(client, repo, fake_producer):
    repo.add("Stock")  # fake_producer 沒有 crawl.tasks 的 metadata

    assert client.post("/boards/Stock/crawl").status_code == 202
    assert "partition" not in fake_producer.produced[0]
