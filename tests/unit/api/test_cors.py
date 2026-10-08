ALLOWED = "https://radar.example.com"


def preflight(client, origin, method="POST"):
    return client.options(
        "/boards",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "Content-Type",
        },
    )


def test_default_allows_no_cross_origin(make_client):
    response = preflight(make_client(), ALLOWED)

    assert "access-control-allow-origin" not in response.headers


def test_configured_origin_passes_preflight(make_client):
    response = preflight(make_client([ALLOWED]), ALLOWED)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED


def test_unlisted_origin_rejected(make_client):
    response = preflight(make_client([ALLOWED]), "https://evil.example.com")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_disallowed_method_rejected(make_client):
    response = preflight(make_client([ALLOWED]), ALLOWED, method="DELETE")

    assert response.status_code == 400


def test_simple_request_gets_allow_origin_header(make_client, repo):
    repo.add("Stock")

    response = make_client([ALLOWED]).get("/boards", headers={"Origin": ALLOWED})

    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "access-control-allow-credentials" not in response.headers
