from confluent_kafka import KafkaException
from fastapi import APIRouter, HTTPException, status

from radar.api.deps import Producer, Repository
from radar.api.kafka_ops import dispatch_task, make_manual_list_task
from radar.api.repository import BoardExistsError, BoardNotFoundError
from radar.api.schemas import BoardCreate, BoardOut, BoardUpdate, CrawlAccepted
from radar.common.kafka.producer import DeliveryError
from radar.common.log import log

router = APIRouter(prefix="/boards", tags=["boards"])


@router.get("", response_model=list[BoardOut])
def list_boards(repo: Repository) -> list[BoardOut]:
    """Scheduler 每 30 秒呼叫一次（設計文件 4.4）。"""
    return [BoardOut.model_validate(b) for b in repo.list_all()]


@router.post("", response_model=BoardOut, status_code=status.HTTP_201_CREATED)
def create_board(data: BoardCreate, repo: Repository) -> BoardOut:
    try:
        board = repo.create(data)
    except BoardExistsError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, f"board {data.board} already exists") from e
    log.info("board created: %s interval=%ss", board.board, board.interval_sec)
    return BoardOut.model_validate(board)


@router.patch("/{board}", response_model=BoardOut)
def update_board(board: str, data: BoardUpdate, repo: Repository) -> BoardOut:
    try:
        updated = repo.update(board, data)
    except BoardNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"board {board} not found") from e
    log.info("board updated: %s %s", board, data.changes())
    return BoardOut.model_validate(updated)


@router.post("/{board}/crawl", response_model=CrawlAccepted, status_code=status.HTTP_202_ACCEPTED)
def trigger_crawl(board: str, repo: Repository, producer: Producer) -> CrawlAccepted:
    """手動觸發：直接寫入 crawl.tasks，停用中的看板也允許。"""
    try:
        repo.get(board)
    except BoardNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"board {board} not found") from e
    task = make_manual_list_task(board)
    try:
        dispatch_task(producer, task)
    except (DeliveryError, TimeoutError, KafkaException, BufferError) as e:
        log.error("manual crawl dispatch failed for %s: %s", board, e)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "kafka unavailable") from e
    log.info("manual crawl dispatched: %s task=%s", board, task.task_id)
    return CrawlAccepted(task_id=str(task.task_id), board=board)
