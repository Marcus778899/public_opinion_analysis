import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.kafka import names

NOW = datetime(2026, 10, 29, 3, 0, tzinfo=UTC)


def _load() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "tools" / "recrawl_posts.py"
    spec = importlib.util.spec_from_file_location("recrawl_posts", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load()


def test_parse_post_ids_blank_and_duplicate_lines_are_dropped_in_order() -> None:
    raw = ["Stock.M.1791443988.A.A0F\n", "  \n", "Gossiping.M.1.A.001", "Stock.M.1791443988.A.A0F"]
    assert tool.parse_post_ids(raw) == ["Stock.M.1791443988.A.A0F", "Gossiping.M.1.A.001"]


def test_parse_post_ids_bad_format_raises() -> None:
    with pytest.raises(ValueError):
        tool.parse_post_ids(["Stock.M.1791443988.A.A0F", "not-a-post-id"])


def test_build_tasks_makes_recrawl_post_task_with_ptt_url() -> None:
    (task,) = tool.build_tasks(["Gossiping.M.1792234882.A.EE7"], NOW)
    assert task.type is CrawlTaskType.POST
    assert task.reason is CrawlReason.RECRAWL
    assert task.board == "Gossiping"
    assert task.url == "https://www.ptt.cc/bbs/Gossiping/M.1792234882.A.EE7.html"
    assert task.kafka_key() == "Gossiping.M.1792234882.A.EE7"
    assert task.created_at == NOW


def test_build_tasks_empty_returns_empty() -> None:
    assert tool.build_tasks([], NOW) == []


def test_send_tasks_sends_each_to_crawl_tasks_and_flushes() -> None:
    producer = MagicMock()
    tasks = tool.build_tasks(["Stock.M.1791443988.A.A0F", "Tech_Job.M.1792498878.A.7D2"], NOW)
    assert tool.send_tasks(producer, tasks) == 2
    topics = [c.args[0] for c in producer.send.call_args_list]
    keys = [c.args[1] for c in producer.send.call_args_list]
    assert topics == [names.CRAWL_TASKS] * 2
    assert keys == ["Stock.M.1791443988.A.A0F", "Tech_Job.M.1792498878.A.7D2"]
    producer.flush.assert_called_once()


def test_read_ids_merges_args_and_file(tmp_path: Path) -> None:
    f = tmp_path / "ids.txt"
    f.write_text("Stock.M.1791443988.A.A0F\nTech_Job.M.1792498878.A.7D2\n", encoding="utf-8")
    args = tool.parse_args(["Stock.M.1791443988.A.A0F", "--file", str(f)])
    assert tool.read_ids(args) == ["Stock.M.1791443988.A.A0F", "Tech_Job.M.1792498878.A.7D2"]
