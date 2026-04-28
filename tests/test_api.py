import os
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

TEST_GRAPH = "codebase_test"


@pytest.fixture(scope="module")
def client(age_conn):
    import config
    config.AGE_GRAPH = TEST_GRAPH

    import core.age_queries as q
    q.init(os.environ["AGE_DSN"], TEST_GRAPH)

    from api.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_get_node_found(client):
    r = client.get("/graph/node/UserService")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "UserService"
    assert data["file_type"] == "code"


def test_get_node_missing(client):
    r = client.get("/graph/node/NonExistent____")
    assert r.status_code == 404


def test_get_neighbors(client):
    r = client.get("/graph/neighbors/UserService?depth=1")
    assert r.status_code == 200
    ids = [n["node"]["id"] for n in r.json()]
    assert "UserRepo" in ids
    assert "Article" in ids


def test_get_community(client):
    r = client.get("/graph/community/0")
    assert r.status_code == 200
    ids = [n["id"] for n in r.json()]
    assert "UserService" in ids
    assert "UserRepo" in ids
    assert "Article" not in ids


def test_god_nodes(client):
    r = client.get("/graph/god-nodes?limit=5")
    assert r.status_code == 200
    nodes = r.json()
    assert len(nodes) >= 1
    assert nodes[0]["id"] == "UserService"


def test_graph_stats(client):
    r = client.get("/graph/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["nodes"] >= 4
    assert data["edges"] >= 2


def test_shortest_path_found(client):
    r = client.get("/graph/path?src=UserService&dst=Article")
    assert r.status_code == 200
    path = r.json()
    assert len(path) >= 2


def test_shortest_path_not_found(client):
    r = client.get("/graph/path?src=UserService&dst=README")
    assert r.status_code == 404


def test_keyword_search(client):
    r = client.post("/graph/search", json={"keywords": ["user"], "hops": 1})
    assert r.status_code == 200
    ids = [n["id"] for n in r.json()]
    assert "UserService" in ids
    assert "UserRepo" in ids


def test_keyword_search_no_results(client):
    r = client.post("/graph/search", json={"keywords": ["xyznotexist"], "hops": 1})
    assert r.status_code == 200
    assert r.json() == []


def test_api_key_rejected(age_conn):
    import config
    config.API_KEY = "secret"
    config.AGE_GRAPH = TEST_GRAPH

    import core.age_queries as q
    q.init(os.environ["AGE_DSN"], TEST_GRAPH)

    from api.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        r = c.get("/graph/stats")
        assert r.status_code == 401
        r2 = c.get("/graph/stats", headers={"X-Api-Key": "secret"})
        assert r2.status_code == 200

    config.API_KEY = ""
