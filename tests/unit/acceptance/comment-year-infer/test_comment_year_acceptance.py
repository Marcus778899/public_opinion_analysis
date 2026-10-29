"""#179：推文時間補年份不可落在未來（開發規格 2.1）。只經 parse_post_page 測對外行為。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from radar.collector.parsers.ptt import parse_post_page

# NOTE: 容許值（爬取時間之後多久內仍算合理）：時鐘誤差與跨時區邊界，取 1 天
TOLERANCE = timedelta(days=1)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _html(post_local: datetime, comment_times: list[str]) -> str:
    month = _MONTHS[post_local.month - 1]
    header = f"Mon {month} {post_local.day:2d} {post_local:%H:%M:%S} {post_local.year}"
    pushes = "".join(
        f'<div class="push"><span class="push-tag">推 </span>'
        f'<span class="push-userid">u{i}</span>'
        f'<span class="push-content">: hi</span>'
        f'<span class="push-ipdatetime"> {t}</span></div>'
        for i, t in enumerate(comment_times)
    )
    return (
        '<html><body><div id="main"><div id="main-content">'
        '<div class="article-metaline"><span class="article-meta-tag">作者</span>'
        '<span class="article-meta-value">a (b)</span></div>'
        '<div class="article-metaline"><span class="article-meta-tag">標題</span>'
        '<span class="article-meta-value">t</span></div>'
        f'<div class="article-metaline"><span class="article-meta-tag">時間</span>'
        f'<span class="article-meta-value">{header}</span></div>'
        f"內文\n{pushes}</div></div></body></html>"
    )


def _parse(post_local: datetime, crawled_at: datetime, times: list[str]):
    post = parse_post_page(
        _html(post_local, times),
        board="Stock",
        url="https://www.ptt.cc/bbs/Stock/M.1791345103.A.E41.html",
        crawled_at=crawled_at,
        task_id=uuid.uuid4(),
    )
    return [c.commented_at for c in post.comments]


def _taipei(y, m, d, h=12):
    return datetime(y, m, d, h, 0)


def test_dec_post_jan_comment_goes_to_next_year():
    (t,) = _parse(_taipei(2026, 12, 31, 23), datetime(2027, 1, 2, tzinfo=UTC), ["01/01 00:10"])
    assert t == datetime(2026, 12, 31, 16, 10, tzinfo=UTC)


def test_jan_post_jan_comment_stays_same_year():
    (t,) = _parse(_taipei(2026, 1, 5), datetime(2026, 1, 20, tzinfo=UTC), ["01/06 10:00"])
    assert t == datetime(2026, 1, 6, 2, 0, tzinfo=UTC)


def test_oct_post_nov_comment_stays_same_year():
    (t,) = _parse(_taipei(2026, 10, 20), datetime(2026, 11, 10, tzinfo=UTC), ["11/05 10:00"])
    assert t == datetime(2026, 11, 5, 2, 0, tzinfo=UTC)


def test_comment_later_than_crawl_time_is_not_in_the_future():
    crawled = datetime(2026, 10, 29, tzinfo=UTC)
    (t,) = _parse(_taipei(2026, 10, 7), crawled, ["11/05 10:00"])
    assert t is None or t <= crawled + TOLERANCE


@pytest.mark.parametrize("stamp", ["09/30 10:00", "10/07 12:30", "10/29 08:00", "01/02 03:04"])
def test_normal_comments_never_exceed_crawl_time_plus_tolerance(stamp):
    crawled = datetime(2026, 10, 29, 6, 0, tzinfo=UTC)
    (t,) = _parse(_taipei(2026, 10, 7), crawled, [stamp])
    assert t is None or t <= crawled + TOLERANCE


@pytest.mark.parametrize("stamp", ["13/45 99:99", "02/30 10:00", "02/29 10:00", "abc", ""])
def test_malformed_comment_time_never_yields_future(stamp):
    crawled = datetime(2027, 1, 20, tzinfo=UTC)
    (t,) = _parse(_taipei(2027, 1, 5), crawled, [stamp])
    assert t is None or t <= crawled + TOLERANCE


def test_one_bad_comment_does_not_affect_others():
    crawled = datetime(2026, 10, 29, tzinfo=UTC)
    ts = _parse(_taipei(2026, 10, 7), crawled, ["10/08 10:00", "bad", "11/30 10:00"])
    assert ts[0] == datetime(2026, 10, 8, 2, 0, tzinfo=UTC)
    assert ts[1] is None
    assert ts[2] is None or ts[2] <= crawled + TOLERANCE


class _RecLog:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str, *args: object, **kwargs: object) -> None:
        self.warnings.append(msg)

    def __getattr__(self, name: str):
        return lambda *a, **k: None


@pytest.fixture
def rec_log(monkeypatch):
    from radar.collector.parsers import ptt as ptt_module

    rec = _RecLog()
    monkeypatch.setattr(ptt_module, "log", rec)
    return rec


def test_unreasonable_comment_time_logs_one_warning(rec_log):
    crawled = datetime(2026, 10, 29, tzinfo=UTC)
    (t,) = _parse(_taipei(2026, 10, 28), crawled, ["11/05 10:00"])
    assert t is None
    assert len(rec_log.warnings) == 1


def test_normal_and_stepped_back_comment_time_logs_no_warning(rec_log):
    crawled = datetime(2026, 10, 29, tzinfo=UTC)
    _parse(_taipei(2026, 10, 7), crawled, ["10/08 10:00", "11/05 10:00"])
    assert rec_log.warnings == []
