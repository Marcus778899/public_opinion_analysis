"""Scheduler（設計文件 4.4）：依看板設定派發列表任務，並定期派發到期的重爬任務。

只能跑 1 個 instance：啟動時取得 PG advisory lock，取不到就等待（standby）。
"""

import functools
import signal
import threading
from collections.abc import Callable
from datetime import UTC, datetime

import httpx2
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from confluent_kafka import KafkaException
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from radar.api.schemas import BoardOut
from radar.collector.recrawl import DuePostDispatcher
from radar.common.db.session import make_engine, make_session_factory
from radar.common.enums import CrawlReason
from radar.common.kafka import names
from radar.common.kafka.producer import DeliveryError, JsonProducer
from radar.common.log import log, setup_logging
from radar.common.settings import SchedulerSettings, get_kafka_settings, get_postgres_settings
from radar.common.tasks import make_list_task

ADVISORY_LOCK_KEY = 7_200_001  # 任意固定值，只用於 Scheduler
BOARD_JOB_PREFIX = "board:"
BOARD_JOB_JITTER_SEC = 5
LOCK_HEARTBEAT_SEC = 30


class BoardsClient:
    """向 API 取得看板設定；失敗回傳 None，呼叫端維持現有計時器（設計文件 4.4）。"""

    def __init__(
        self,
        api_url: str,
        *,
        timeout_s: float = 5.0,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._client = httpx2.Client(base_url=api_url, timeout=timeout_s, transport=transport)

    def fetch(self) -> list[BoardOut] | None:
        try:
            response = self._client.get("/boards")
            response.raise_for_status()
            return [BoardOut.model_validate(b) for b in response.json()]
        except (httpx2.HTTPError, ValueError, ValidationError) as e:
            log.warning("fetch boards failed, keeping current timers: %r", e)
            return None

    def close(self) -> None:
        self._client.close()


def sync_board_jobs(
    scheduler: BaseScheduler, boards: list[BoardOut], send_list_task: Callable[[str], None]
) -> None:
    """依看板設定新增、移除或調整計時器；只在有變化時動作。

    - 啟用且沒有計時器 → 新增，並立刻執行一次
    - 停用、或已從 API 消失 → 移除
    - interval_sec 改變 → reschedule（從當下重新起算）
    """
    wanted = {b.board: b for b in boards if b.enabled}
    for job in scheduler.get_jobs():
        if job.id.startswith(BOARD_JOB_PREFIX) and job.id[len(BOARD_JOB_PREFIX) :] not in wanted:
            job.remove()
            log.info("board timer removed: %s", job.id)
    for name, board in wanted.items():
        job_id = f"{BOARD_JOB_PREFIX}{name}"
        job = scheduler.get_job(job_id)
        if job is None:
            scheduler.add_job(
                send_list_task,
                "interval",
                seconds=board.interval_sec,
                jitter=BOARD_JOB_JITTER_SEC,
                id=job_id,
                args=[name],
                next_run_time=datetime.now(UTC),
            )
            log.info("board timer added: %s every %ss", name, board.interval_sec)
        elif job.trigger.interval.total_seconds() != board.interval_sec:
            scheduler.reschedule_job(
                job_id, trigger="interval", seconds=board.interval_sec, jitter=BOARD_JOB_JITTER_SEC
            )
            log.info("board timer rescheduled: %s every %ss", name, board.interval_sec)


def make_list_task_sender(producer: JsonProducer) -> Callable[[str], None]:
    """回傳 send_list_task(board)：送出 reason=schedule 的列表任務並 flush。"""

    def send_list_task(board: str) -> None:
        task = make_list_task(board, CrawlReason.SCHEDULE)
        try:
            producer.send(names.CRAWL_TASKS, task.kafka_key(), task)
            producer.flush()
        except (DeliveryError, TimeoutError, KafkaException, BufferError) as e:
            # 不讓計時器停掉；下一次觸發再送
            log.error("dispatch list task failed for %s: %s", board, e)

    return send_list_task


class AdvisoryLock:
    """PG session 層級的 advisory lock；用獨立連線持有，連線斷掉鎖就釋放。"""

    def __init__(self, engine: Engine, key: int = ADVISORY_LOCK_KEY) -> None:
        self._engine = engine
        self._key = key
        self._conn: Connection | None = None

    def try_acquire(self) -> bool:
        if self._conn is None:
            self._conn = self._engine.connect()
        acquired = self._conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": self._key}
        ).scalar_one()
        # 結束隱含的 transaction；session 層級的鎖不受 commit 影響
        self._conn.commit()
        return bool(acquired)

    def wait_until_acquired(
        self, poll_s: float = 10.0, stop: Callable[[], bool] = lambda: False
    ) -> bool:
        """取到鎖回傳 True；stop() 為 True 時放棄並回傳 False。"""
        announced = False
        while not stop():
            if self.try_acquire():
                log.info("advisory lock acquired, scheduler is active")
                return True
            if not announced:
                log.info("another scheduler holds the lock, standing by")
                announced = True
            threading.Event().wait(poll_s)
        return False

    def is_held(self) -> bool:
        """持有鎖的連線還活著、且鎖仍屬於這條連線。"""
        if self._conn is None:
            return False
        try:
            held = self._conn.execute(
                text(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                    "AND pid = pg_backend_pid() AND objid = :key AND granted"
                ),
                {"key": self._key},
            ).scalar_one()
            self._conn.commit()
        except DBAPIError:
            return False
        return held > 0

    def release(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self._key})
            self._conn.commit()
        except DBAPIError:
            pass  # 連線已斷，鎖早已隨連線釋放
        finally:
            self._conn.close()
            self._conn = None


def _logged(fn: Callable[[], object]) -> Callable[[], None]:
    """計時器工作的例外只記錄，不讓 APScheduler 印出 traceback 後繼續；下次觸發再試。"""

    @functools.wraps(fn)
    def wrapper() -> None:
        try:
            fn()
        except Exception:
            log.exception("scheduled job %s failed", getattr(fn, "__name__", fn))

    return wrapper


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("scheduler")
    settings = SchedulerSettings()
    engine = make_engine(get_postgres_settings())
    lock = AdvisoryLock(engine)
    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    if not lock.wait_until_acquired(stop=stopping.is_set):
        engine.dispose()
        return

    producer = JsonProducer(get_kafka_settings())
    boards = BoardsClient(settings.api_url)
    scheduler = BlockingScheduler(
        timezone=UTC,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 30},
    )
    sender = make_list_task_sender(producer)
    dispatcher = DuePostDispatcher(
        make_session_factory(engine),
        producer,
        limit=settings.due_posts_limit,
        time_scale=settings.time_scale,
    )

    def sync_boards() -> None:
        fetched = boards.fetch()
        if fetched is not None:
            sync_board_jobs(scheduler, fetched, sender)

    def lock_heartbeat() -> None:
        if not lock.is_held():
            log.critical("advisory lock lost, stopping scheduler")
            scheduler.shutdown(wait=False)

    scheduler.add_job(
        _logged(sync_boards),
        "interval",
        seconds=settings.sync_interval_sec,
        id="sync_boards",
        next_run_time=datetime.now(UTC),
    )
    scheduler.add_job(
        _logged(dispatcher), "interval", seconds=settings.due_posts_interval_sec, id="due_posts"
    )
    scheduler.add_job(_logged(lock_heartbeat), "interval", seconds=LOCK_HEARTBEAT_SEC, id="lock")
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: scheduler.shutdown(wait=False))
    try:
        scheduler.start()
    finally:
        log.info("scheduler stopping")
        lock.release()
        producer.flush()
        boards.close()
        engine.dispose()


if __name__ == "__main__":
    main()
