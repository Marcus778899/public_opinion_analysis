"""階段 3 的 ClickHouse 查詢（抽樣、匯出、交叉比對）在真的 ClickHouse 上的行為。

不需要 Kafka：直接把資料寫進 posts_latest、labels。Kafka engine 表連不上 broker 只會記 log。
"""

import time
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr
from testcontainers.core.container import DockerContainer

from radar.common.clickhouse import ClickHouseClient, apply_pending, load_migrations
from radar.common.enums import Polarity
from radar.common.settings import ClickHouseSettings
from radar.ml.experiments.push_ratio import fetch_votes
from radar.ml.labeling.cross_check import fetch_whole_post_labels
from radar.ml.labeling.manual import MANUAL_LABELER, export_batch, read_batch
from radar.ml.labeling.sampling import SampleSpec, fetch_posts, sample_posts
from radar.ml.training.export import fetch_rows

REPO = Path(__file__).resolve().parents[3]
CH_DIR = REPO / "infra/clickhouse"
TS = "'2026-10-07 00:00:00'"


@pytest.fixture(scope="module")
def ch():
    container = (
        DockerContainer("clickhouse/clickhouse-server:26.8")
        .with_env("CLICKHOUSE_USER", "radar")
        .with_env("CLICKHOUSE_PASSWORD", "it")
        .with_env("CLICKHOUSE_DB", "radar")
        .with_volume_mapping(
            str(CH_DIR / "config.d/named_collections.xml"),
            "/etc/clickhouse-server/config.d/named_collections.xml",
        )
        .with_volume_mapping(
            str(CH_DIR / "users.d/radar.xml"), "/etc/clickhouse-server/users.d/radar.xml"
        )
        .with_exposed_ports(8123)
    )
    with container:
        url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8123)}"
        deadline = time.monotonic() + 60
        while True:
            try:
                if httpx2.get(f"{url}/ping").status_code == 200:
                    break
            except httpx2.TransportError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError("clickhouse not ready")
            time.sleep(1)
        client = ClickHouseClient(
            ClickHouseSettings(url=url, db="radar", user="radar", password=SecretStr("it"))
        )
        apply_pending(client, load_migrations(CH_DIR / "migrations"))
        seed(client)
        yield client
        client.close()


def seed(client: ClickHouseClient) -> None:
    posts = []
    for board, n in (("Stock", 6), ("Gossiping", 6)):
        for i in range(n):
            content = "短" if i == 0 else f"{board} 第 {i} 篇的內文，長度足夠拿來標註情緒"
            posts.append(
                f"('{board}.M.{i}.A.1', '{board}', 't{i}', '{content}', 'u', {i * 10}, {i}, "
                f"{TS}, {TS}, false, 1)"
            )
    long_text = "這篇內文的長度足夠拿來標註情緒"
    posts.append(
        f"('Stock.M.99.A.1', 'Stock', 'del', '{long_text}', 'u', 0, 0, {TS}, {TS}, true, 1)"
    )
    # 同一篇的舊版本（lsn 較小）應被 FINAL 去掉
    posts.append(
        f"('Stock.M.1.A.1', 'Stock', 'old', '{long_text}', 'u', 0, 0, {TS}, {TS}, false, 0)"
    )
    client.execute(
        "INSERT INTO posts_latest (post_id, board, title, content, url, push_count, boo_count, "
        "created_at, crawled_at, is_deleted, lsn) VALUES " + ", ".join(posts)
    )
    labels = [
        ("Stock.M.1.A.1", "groq:q", "2026-10-07 01:00:00", None, "negative"),
        ("Stock.M.1.A.1", "groq:q", "2026-10-07 02:00:00", None, "positive"),  # 重標，取最新
        ("Stock.M.1.A.1", "groq:q", "2026-10-07 02:00:00", "台積電", "positive"),
        ("Stock.M.2.A.1", "groq:q", "2026-10-07 01:00:00", None, "neutral"),
        ("Stock.M.2.A.1", MANUAL_LABELER, "2026-10-07 01:00:00", None, "negative"),
        ("Gossiping.M.3.A.1", "groq:q", "2026-10-07 01:00:00", None, "negative"),
    ]
    values = ", ".join(
        f"('{p}', '{lab}', 'prompt-v4', '{ts}', {'NULL' if t is None else repr(t)}, '{pol}')"
        for p, lab, ts, t, pol in labels
    )
    cols = "post_id, labeler, version, labeled_at, target, polarity"
    client.execute(f"INSERT INTO labels ({cols}) VALUES {values}")


def test_sample_posts_stratified_by_board_and_stable_for_seed(ch):
    spec = SampleSpec(per_board=3, seed=1)

    first = sample_posts(ch, spec, set())
    again = sample_posts(ch, spec, set())

    assert [p.post_id for p in first] == [p.post_id for p in again]
    assert sorted({p.board for p in first}) == ["Gossiping", "Stock"]
    assert all(sum(p.board == b for p in first) == 3 for b in ("Stock", "Gossiping"))
    ids = {p.post_id for p in first}
    assert "Stock.M.0.A.1" not in ids and "Stock.M.99.A.1" not in ids  # 太短、已刪除


def test_sample_posts_uses_latest_version_and_respects_board_filter(ch):
    posts = sample_posts(ch, SampleSpec(per_board=10, seed=1, boards=["Stock"]), set())

    assert {p.board for p in posts} == {"Stock"}
    titles = {p.post_id: p.title for p in posts}
    assert titles["Stock.M.1.A.1"] == "t1"


def test_sample_posts_skips_already_labeled(ch):
    spec = SampleSpec(per_board=10, seed=1, skip_labeler="groq:q", skip_version="prompt-v4")

    ids = {p.post_id for p in sample_posts(ch, spec, set())}

    assert not ids & {"Stock.M.1.A.1", "Stock.M.2.A.1", "Gossiping.M.3.A.1"}
    assert "Stock.M.3.A.1" in ids


def test_fetch_posts_by_ids(ch):
    posts = fetch_posts(ch, ["Stock.M.2.A.1", "missing"])

    assert list(posts) == ["Stock.M.2.A.1"]


def test_fetch_whole_post_labels_takes_latest_and_ignores_targets(ch):
    labels = fetch_whole_post_labels(ch, "groq:q", "prompt-v4")

    assert labels == {
        "Stock.M.1.A.1": Polarity.POSITIVE,
        "Stock.M.2.A.1": Polarity.NEUTRAL,
        "Gossiping.M.3.A.1": Polarity.NEGATIVE,
    }


def test_fetch_rows_joins_latest_label_and_post(ch):
    rows = {r["post_id"]: r for r in fetch_rows(ch, "groq:q", "prompt-v4")}

    assert set(rows) == {"Stock.M.1.A.1", "Stock.M.2.A.1", "Gossiping.M.3.A.1"}
    assert (rows["Stock.M.1.A.1"]["polarity"], rows["Stock.M.1.A.1"]["title"]) == ("positive", "t1")


def test_fetch_votes_joins_counts(ch):
    votes = {v.post_id: v for v in fetch_votes(ch, "groq:q", "prompt-v4")}

    assert (votes["Stock.M.2.A.1"].push_count, votes["Stock.M.2.A.1"].boo_count) == (20, 2)


def test_export_batch_only_primary_labeled_without_manual(ch, tmp_path):
    now = datetime(2026, 10, 7, tzinfo=UTC)

    path = export_batch(ch, "groq:q", 10, set(), 100, tmp_path, now=now)

    assert {p.post_id for p in read_batch(path)} == {"Stock.M.1.A.1", "Gossiping.M.3.A.1"}
