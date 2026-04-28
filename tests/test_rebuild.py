import os
import time
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

TEST_GRAPH = "codebase_test"


@pytest.fixture(scope="module")
def client(age_conn):
    import config
    config.AGE_GRAPH = TEST_GRAPH
    config.API_KEY = ""

    import core.age_queries as q
    q.init(os.environ["AGE_DSN"], TEST_GRAPH)

    from api.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_rebuild_triggers_flag(client):
    from api.main import rebuild_flag

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("api.routes.rebuild.run_loader") as mock_loader:
        mock_loader.return_value = None
        r = client.post("/rebuild/")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        # wait for background thread to finish
        for _ in range(20):
            if not rebuild_flag["running"]:
                break
            time.sleep(0.1)

    assert rebuild_flag["running"] is False


def test_rebuild_503_during_run(client):
    from api.main import rebuild_flag
    rebuild_flag["running"] = True
    r = client.get("/graph/stats")
    assert r.status_code == 503
    rebuild_flag["running"] = False
