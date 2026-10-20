import uuid
from datetime import UTC, datetime, timedelta

import pytest

from radar.bot.stats import BoardOverview, HotPost, PostSentiment, PostStats
from radar.bot.views import (
    MAX_CALLBACK_BYTES,
    Action,
    Callback,
    ChatPrefs,
    alert_screen,
    board_overview_screen,
    board_picker_screen,
    controversy,
    encode_callback,
    escape,
    expired_screen,
    hot_screen,
    main_menu,
    parse_callback,
    post_line,
    post_url,
    ratio,
    sentiment_text,
    settings_screen,
    subscriptions_screen,
)
from radar.common.schemas import Alert

PID = "HatePolitics.M.1792217249.A.400"
PID2 = "HatePolitics.M.1792217250.A.401"
NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)
MIN = 0.6


def stats(post_id=PID, *, title="[新聞] 測試", push=30, boo=10, arrow=5, sentiment=None):
    return PostStats(post_id, post_id.split(".", 1)[0], title, push, boo, arrow, sentiment)


def alert(unit_type="post", samples=(PID,), value=90, baseline=4.5) -> Alert:
    return Alert(
        alert_id=uuid.UUID(int=1),
        unit_type=unit_type,
        unit_key=PID if unit_type == "post" else "HatePolitics",
        board="HatePolitics",
        window_start=NOW - timedelta(minutes=10),
        window_end=NOW,
        value=value,
        baseline=baseline,
        zscore=9.1,
        sample_post_ids=list(samples),
        created_at=NOW,
    )


def callbacks(screen) -> list[str]:
    return [b.callback_data for row in screen.keyboard for b in row if b.callback_data]


def urls(screen) -> list[str]:
    return [b.url for row in screen.keyboard for b in row if b.url]


def test_post_url_builds_ptt_link():
    assert post_url(PID) == "https://www.ptt.cc/bbs/HatePolitics/M.1792217249.A.400.html"


# --- callback_data（S6-03） ---


def test_encode_callback_format():
    assert encode_callback(Action.SUB, "Gossiping") == "1:sub:Gossiping"


def test_encode_then_parse_roundtrip_with_post_id():
    assert parse_callback(encode_callback(Action.MUTE, PID)) == Callback(Action.MUTE, PID)


def test_encode_callback_too_long_rejected():
    with pytest.raises(ValueError):
        encode_callback(Action.MUTE, "x" * MAX_CALLBACK_BYTES)


def test_encode_callback_counts_bytes_not_chars():
    with pytest.raises(ValueError):
        encode_callback(Action.SUB, "看" * 20)  # 60 bytes + 前綴


@pytest.mark.parametrize("data", [None, "", "0:sub:Stock", "1:nope:x", "garbage", "1:sub"])
def test_parse_callback_invalid_returns_none(data):
    assert parse_callback(data) is None


def test_parse_callback_arg_may_be_empty():
    assert parse_callback("1:menu:") == Callback(Action.MENU, "")


def test_expired_screen_is_main_menu_with_notice():
    screen = expired_screen()

    assert "過期" in screen.text
    assert screen.keyboard == main_menu().keyboard


# --- 格式（S6-01、S6-05） ---


def test_escape_only_html_special_chars():
    assert escape('<b>A&B</b> "q"') == '&lt;b&gt;A&amp;B&lt;/b&gt; "q"'


@pytest.mark.parametrize(
    ("value", "baseline", "expected"), [(90, 4.5, 20), (30, 0.2, 30), (0, 0, 0)]
)
def test_ratio_floors_baseline_at_one(value, baseline, expected):
    assert ratio(value, baseline) == expected


def test_controversy_is_boo_share():
    assert controversy(30, 10) == 0.25


def test_controversy_below_min_votes_is_none():
    assert controversy(6, 3) is None


def test_controversy_at_min_votes_is_shown():
    assert controversy(5, 5) == 0.5


def test_sentiment_text_confident():
    assert sentiment_text(PostSentiment("negative", 0.72), MIN) == "負面 72%"


def test_sentiment_text_below_min_is_uncertain():
    assert sentiment_text(PostSentiment("positive", 0.59), MIN) == "不確定"


def test_sentiment_text_at_min_is_confident():
    assert sentiment_text(PostSentiment("neutral", 0.6), MIN) == "中立 60%"


def test_sentiment_text_missing_is_none_yet():
    assert sentiment_text(None, MIN) == "尚無"


def test_post_line_escapes_title_and_links_post():
    line = post_line(stats(title="<script>"), MIN)

    assert "&lt;script&gt;" in line
    assert f'href="{post_url(PID)}"' in line


def test_post_line_has_counts_controversy_and_sentiment():
    line = post_line(stats(sentiment=PostSentiment("negative", 0.8)), MIN)

    assert all(s in line for s in ("推 30", "噓 10", "→ 5", "爭議 25%", "負面 80%"))


def test_post_line_low_votes_hides_controversy():
    assert "爭議" not in post_line(stats(push=3, boo=1), MIN)


def test_post_line_missing_title_uses_post_id():
    assert PID in post_line(stats(title=None), MIN)


# --- 主選單與畫面（S6-04） ---


def test_main_menu_has_four_entries():
    assert callbacks(main_menu()) == ["1:hot:", "1:subs:", "1:boards:", "1:set:"]


def test_main_menu_notice_shown_first():
    assert main_menu("已訂閱 Stock").text.startswith("已訂閱 Stock")


def test_hot_screen_lists_posts_with_url_buttons():
    posts = [HotPost(stats(PID), 40), HotPost(stats(PID2), 20)]

    screen = hot_screen(posts, all_boards=False, min_score=MIN)

    assert screen.text.index("40") < screen.text.index("20")
    assert urls(screen) == [post_url(PID), post_url(PID2)]


def test_hot_screen_toggles_scope():
    assert "1:hot:all" in callbacks(hot_screen([], all_boards=False, min_score=MIN))
    assert "1:hot:" in callbacks(hot_screen([], all_boards=True, min_score=MIN))


def test_hot_screen_empty_says_no_comments():
    assert "最近沒有推文" in hot_screen([], all_boards=True, min_score=MIN).text


def test_subscriptions_screen_marks_subscribed_boards():
    screen = subscriptions_screen(["Gossiping", "Stock"], {"Stock"})

    labels = [b.text for row in screen.keyboard for b in row]
    assert "⬜ Gossiping" in labels and "✅ Stock" in labels
    assert "1:sub:Stock" in callbacks(screen)


def test_subscriptions_screen_no_boards():
    assert "沒有可訂閱的看板" in subscriptions_screen([], set()).text


def test_board_picker_has_overview_button_per_board():
    assert callbacks(board_picker_screen(["Gossiping", "Stock"]))[:2] == [
        "1:ov:Gossiping",
        "1:ov:Stock",
    ]


def overview(sentiments=None, top=()) -> BoardOverview:
    return BoardOverview(
        board="Stock",
        posts_24h=35,
        comments_24h=1200,
        sentiments=sentiments if sentiments is not None else {"negative": 6, "neutral": 3},
        top_controversial=list(top),
        alerts_today=2,
    )


def test_board_overview_shows_counts_and_sentiment_share():
    text = board_overview_screen(overview(), MIN).text

    assert all(s in text for s in ("35 篇", "1200 則", "負面 67%", "中立 33%", "正面 0%"))
    assert "9 篇有推論" in text
    assert "今天 2 則警示" in text


def test_board_overview_no_predictions_says_none_yet():
    assert "尚無推論" in board_overview_screen(overview(sentiments={}), MIN).text


def test_board_overview_lists_controversial_posts():
    text = board_overview_screen(overview(top=[stats(PID)]), MIN).text

    assert "[新聞] 測試" in text


def test_settings_screen_toggles_and_unmute_buttons():
    screen = settings_screen(ChatPrefs(post_alerts=False), [stats(PID), PID2])

    labels = [b.text for row in screen.keyboard for b in row]
    assert any(label.startswith("⬜ 文章警示") for label in labels)
    assert any(label.startswith("✅ 看板警示") for label in labels)
    assert {"1:tog:post", "1:tog:board", f"1:unmute:{PID}", f"1:unmute:{PID2}"} <= set(
        callbacks(screen)
    )


# --- 警示（S6-05） ---


def test_alert_screen_post_has_ratio_counts_and_sentiment():
    screen = alert_screen(alert(), {PID: stats(sentiment=PostSentiment("negative", 0.8))}, MIN)

    assert "90 則" in screen.text and "平常的 20 倍" in screen.text
    assert "負面 80%" in screen.text
    assert urls(screen) == [post_url(PID)]
    assert {f"1:mute:{PID}", "1:ov:HatePolitics", "1:subs:"} <= set(callbacks(screen))


def test_alert_screen_board_lists_top_three_without_mute_button():
    samples = [f"HatePolitics.M.179221725{i}.A.40{i}" for i in range(4)]

    screen = alert_screen(alert("board", samples), {p: stats(p) for p in samples}, MIN)

    assert screen.text.count("推 30") == 3
    assert not any(c.startswith("1:mute:") for c in callbacks(screen))


def test_alert_screen_without_stats_still_has_basics():
    screen = alert_screen(alert(), {}, MIN)

    assert "90 則" in screen.text
    assert "推 " not in screen.text
    assert urls(screen) == [post_url(PID)]


def test_alert_screen_callback_data_within_limit():
    long_id = "HatePolitics.M.1792217249.A.400"

    for data in callbacks(alert_screen(alert(samples=(long_id,)), {}, MIN)):
        assert len(data.encode()) <= MAX_CALLBACK_BYTES
