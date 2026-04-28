import os
import pytest
from dotenv import load_dotenv

load_dotenv()

TEST_GRAPH = "codebase_test"


def test_fixture_alive(age_conn):
    assert age_conn is not None


def get_q():
    import core.age_queries as q
    q.init(os.environ["AGE_DSN"], TEST_GRAPH)
    return q


def test_get_node_found(age_conn):
    q = get_q()
    node = q.get_node("UserService")
    assert node is not None
    assert node["id"] == "UserService"
    assert node["file_type"] == "code"


def test_get_node_missing(age_conn):
    q = get_q()
    assert q.get_node("NonExistent____") is None


def test_get_neighbors(age_conn):
    q = get_q()
    neighbors = q.get_neighbors("UserService", depth=1)
    ids = [n["node"]["id"] for n in neighbors]
    assert "UserRepo" in ids
    assert "Article" in ids


def test_get_community(age_conn):
    q = get_q()
    members = q.get_community(0)
    ids = [n["id"] for n in members]
    assert "UserService" in ids
    assert "UserRepo" in ids
    assert "Article" not in ids  # community=1


def test_god_nodes(age_conn):
    q = get_q()
    nodes = q.god_nodes(limit=5)
    assert len(nodes) >= 1
    assert nodes[0]["id"] == "UserService"


def test_graph_stats(age_conn):
    q = get_q()
    stats = q.graph_stats()
    assert stats["nodes"] >= 4
    assert stats["edges"] >= 2


def test_shortest_path_found(age_conn):
    q = get_q()
    path = q.shortest_path("UserService", "Article")
    assert path is not None
    assert len(path) >= 2


def test_shortest_path_not_found(age_conn):
    q = get_q()
    path = q.shortest_path("UserService", "README")
    assert path is None or path == []


def test_keyword_search(age_conn):
    q = get_q()
    results = q.keyword_search(["user"], hops=1)
    ids = [n["id"] for n in results]
    assert "UserService" in ids
    assert "UserRepo" in ids


def test_keyword_search_no_results(age_conn):
    q = get_q()
    results = q.keyword_search(["xyznotexist"], hops=1)
    assert results == []
