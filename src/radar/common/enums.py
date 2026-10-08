"""ORM 與 Kafka 訊息共用的列舉值；放在這裡避免兩邊互相 import。"""

from enum import StrEnum


class CommentType(StrEnum):
    PUSH = "push"
    BOO = "boo"
    ARROW = "arrow"


class CrawlTaskType(StrEnum):
    LIST = "list"
    POST = "post"


class CrawlReason(StrEnum):
    SCHEDULE = "schedule"
    MANUAL = "manual"
    RECRAWL = "recrawl"


class Polarity(StrEnum):
    """情緒三分類（設計文件 15.3）。"""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
