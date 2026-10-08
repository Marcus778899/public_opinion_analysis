from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from radar.ml.labeling.human_app import create_app
from radar.ml.labeling.prompt import PostText
from radar.ml.labeling.testset import load_human_labels, write_post_ids

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
IDS = ["Stock.M.1.A.1", "Stock.M.2.A.2"]
WHOLE_NEG = {"target": None, "polarity": "negative"}


@pytest.fixture
def client(tmp_path):
    write_post_ids(tmp_path, IDS)

    def fetch(ids):
        return {i: PostText(i, "Stock", f"標題 {i}", "內文") for i in ids}

    return TestClient(create_app(tmp_path, fetch, now=lambda: NOW)), tmp_path


def test_index_returns_html_without_external_resources(client):
    c, _ = client

    html = c.get("/").text

    assert "<title>人工標註</title>" in html
    assert "http://" not in html and "https://" not in html


def test_next_returns_first_unlabeled_post_and_progress(client):
    c, _ = client

    body = c.get("/api/next").json()

    assert body["item"]["post"]["post_id"] == IDS[0]
    assert body["item"]["index"] == 0
    assert body["progress"] == {"labeled": 0, "total": 2}


def test_post_label_appends_and_advances(client):
    c, testset_dir = client
    payload = {
        "post_id": IDS[0],
        "sentiments": [WHOLE_NEG, {"target": "台積電", "polarity": "negative"}],
        "note": "反串",
    }

    resp = c.post("/api/labels", json=payload)

    assert resp.status_code == 201
    assert resp.json() == {"labeled": 1, "total": 2}
    saved = load_human_labels(testset_dir)[IDS[0]]
    assert (saved.note, saved.labeled_at) == ("反串", NOW)
    assert c.get("/api/next").json()["item"]["post"]["post_id"] == IDS[1]


def test_next_when_all_labeled_returns_none(client):
    c, _ = client
    for pid in IDS:
        c.post("/api/labels", json={"post_id": pid, "sentiments": [WHOLE_NEG]})

    body = c.get("/api/next").json()

    assert body["item"] is None
    assert body["progress"] == {"labeled": 2, "total": 2}


def test_post_at_returns_existing_label_for_relabeling(client):
    c, _ = client
    c.post("/api/labels", json={"post_id": IDS[1], "sentiments": [WHOLE_NEG], "note": "n"})

    body = c.get("/api/posts/1").json()

    assert body["existing"] == [WHOLE_NEG]
    assert body["note"] == "n"


def test_post_at_out_of_range_returns_404(client):
    c, _ = client

    assert c.get("/api/posts/5").status_code == 404


def test_post_label_outside_testset_returns_404(client):
    c, _ = client

    resp = c.post("/api/labels", json={"post_id": "Other.M.1.A.1", "sentiments": [WHOLE_NEG]})

    assert resp.status_code == 404


def test_post_label_invalid_sentiments_returns_422(client):
    c, testset_dir = client
    only_target = [{"target": "x", "polarity": "neutral"}]

    resp = c.post("/api/labels", json={"post_id": IDS[0], "sentiments": only_target})

    assert resp.status_code == 422
    assert load_human_labels(testset_dir) == {}
