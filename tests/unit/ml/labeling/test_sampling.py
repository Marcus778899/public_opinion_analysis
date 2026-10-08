from radar.ml.labeling.sampling import (
    SampleSpec,
    array_param,
    build_sample_query,
    fetch_posts,
    labeled_post_ids,
    sample_posts,
)
from tests.unit.ml.fakes import FakeClickHouse, row


def test_build_sample_query_uses_params_not_literals():
    sql, params = build_sample_query(SampleSpec(per_board=100, seed=7))

    assert "{seed:UInt64}" in sql and "{limit:UInt32}" in sql
    assert "LIMIT {limit:UInt32} BY board" in sql
    assert "100" not in sql and "7" not in sql
    assert params == {"seed": "7", "limit": "100", "min_chars": "20"}


def test_build_sample_query_filters_boards_when_given():
    sql, params = build_sample_query(SampleSpec(per_board=1, seed=1, boards=["Stock", "Tech_Job"]))

    assert "board IN {boards:Array(String)}" in sql
    assert params["boards"] == "['Stock','Tech_Job']"


def test_build_sample_query_skips_labeled_when_given():
    spec = SampleSpec(per_board=1, seed=1, skip_labeler="groq:q", skip_version="prompt-v4")

    sql, params = build_sample_query(spec)

    assert "NOT IN (SELECT post_id FROM labels" in sql
    assert (params["skip_labeler"], params["skip_version"]) == ("groq:q", "prompt-v4")


def test_build_sample_query_extra_per_board_raises_limit():
    _, params = build_sample_query(SampleSpec(per_board=10, seed=1, extra_per_board=3))

    assert params["limit"] == "13"


def test_array_param_escapes_quotes_and_backslashes():
    assert array_param(["it's", "a\\b"]) == "['it\\'s','a\\\\b']"


def test_sample_posts_excludes_testset_ids_and_keeps_per_board_count():
    ch = FakeClickHouse([row("a"), row("t1"), row("b"), row("c"), row("g1", "Gossiping")])

    posts = sample_posts(ch, SampleSpec(per_board=2, seed=1, extra_per_board=1), {"t1"})

    assert [p.post_id for p in posts] == ["a", "b", "g1"]


def test_fetch_posts_empty_ids_skips_query():
    ch = FakeClickHouse()

    assert fetch_posts(ch, []) == {}
    assert ch.queries == []


def test_fetch_posts_returns_by_id():
    ch = FakeClickHouse([row("a"), row("b")])

    posts = fetch_posts(ch, ["a", "b"])

    assert set(posts) == {"a", "b"}
    assert ch.queries[0][1] == {"ids": "['a','b']"}


def test_labeled_post_ids_queries_labeler_version_and_ids():
    ch = FakeClickHouse([{"post_id": "a"}])

    done = labeled_post_ids(ch, "groq:q", "prompt-v4", ["a", "b"])

    sql, params = ch.queries[0]
    assert done == {"a"}
    assert "FROM labels" in sql
    assert params == {"labeler": "groq:q", "version": "prompt-v4", "ids": "['a','b']"}


def test_labeled_post_ids_empty_input_skips_query():
    ch = FakeClickHouse()

    assert labeled_post_ids(ch, "groq:q", "prompt-v4", []) == set()
    assert ch.queries == []
