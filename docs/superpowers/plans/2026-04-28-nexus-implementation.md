# Nexus 서비스 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** graphify 코드베이스 지식그래프를 AGE에서 서빙하는 FastAPI REST API + MCP SSE 서버를 단일 Nexus 서비스로 구축한다.

**Architecture:** `core/age_queries.py`가 psycopg2 ThreadedConnectionPool로 AGE를 쿼리하는 공통 레이어. FastAPI(포트 8004)와 MCP SSE 서버(포트 8006)가 이 레이어를 공유. 모든 FastAPI 핸들러는 `async def` 없이 작성해 스레드풀에서 실행.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, psycopg2-binary, mcp (Anthropic MCP Python SDK), python-dotenv, pytest, httpx

---

## 파일 구조

```
Nexus/
├── config.py                   ← 모든 환경변수 로딩 (단일 진실의 원천)
├── requirements.txt
├── .env.example
├── core/
│   └── age_queries.py          ← ThreadedConnectionPool + 7 쿼리 함수 + 헬퍼
├── api/
│   ├── main.py                 ← FastAPI 앱, lifespan, API Key 의존성, rebuild_flag
│   └── routes/
│       ├── graph.py            ← /query /node /neighbors /community /god-nodes /stats /path
│       └── rebuild.py          ← /rebuild
├── nexus_mcp/                  ← 주의: 'mcp/'가 아닌 'nexus_mcp/' — 설치된 mcp 패키지 shadowing 방지
│   └── server.py               ← MCP SSE 서버 (7개 툴)
├── loader/
│   └── age_loader.py           ← graphify_age_loader.py 이전 (그대로 복사 후 경로 정리)
└── tests/
    ├── conftest.py             ← pytest 픽스처 (test AGE 그래프 셋업/티어다운)
    ├── test_age_queries.py     ← core/ 함수별 통합 테스트 (실제 AGE DB)
    ├── test_api.py             ← REST API 엔드포인트 테스트 (TestClient)
    └── test_rebuild.py         ← rebuild 플래그 + 503 동작 테스트
```

> `api/services/` 폴더가 이미 있다면 무시. 사용하지 않는다.
> `mcp/` 디렉토리를 `nexus_mcp/`으로 사용하는 이유: `mcp/`라는 이름은 설치된 Anthropic MCP Python SDK 패키지명과 충돌해 import가 깨진다.

---

## Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `config.py`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `core/__init__.py`, `api/__init__.py`, `api/routes/__init__.py`, `nexus_mcp/__init__.py`, `loader/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: requirements.txt 작성**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
psycopg2-binary==2.9.9
mcp==1.6.0
python-dotenv==1.0.1
httpx==0.27.0
pytest==8.3.0
pytest-asyncio==0.24.0
starlette==0.41.2
```

- [ ] **Step 2: config.py 작성**

```python
import os
from dotenv import load_dotenv

load_dotenv()

AGE_DSN        = os.environ["AGE_DSN"]
AGE_GRAPH      = os.getenv("AGE_GRAPH", "codebase")
API_PORT       = int(os.getenv("API_PORT", "8004"))
MCP_PORT       = int(os.getenv("MCP_PORT", "8006"))
API_KEY        = os.getenv("API_KEY", "")

GRAPHIFY_PATH     = os.getenv("GRAPHIFY_PATH", "graphify")
SOURCE_DIR        = os.getenv("SOURCE_DIR", ".")
GRAPH_OUTPUT_PATH = os.getenv("GRAPH_OUTPUT_PATH", "graphify-out/graph.json")
```

- [ ] **Step 3: .env.example 작성**

```
AGE_DSN=postgresql://postgres:password@193.168.195.222:5434/lightrag
AGE_GRAPH=codebase
API_PORT=8004
MCP_PORT=8006
API_KEY=change-me-secret-key
GRAPHIFY_PATH=/usr/local/bin/graphify
SOURCE_DIR=/opt/hca-legacy
GRAPH_OUTPUT_PATH=graphify-out/graph.json
```

- [ ] **Step 4: __init__.py 파일 생성**

```bash
touch core/__init__.py api/__init__.py api/routes/__init__.py nexus_mcp/__init__.py loader/__init__.py tests/__init__.py
```

- [ ] **Step 5: 커밋**

```bash
git add config.py requirements.txt .env.example core/__init__.py api/__init__.py api/routes/__init__.py mcp/__init__.py loader/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding — config, requirements, package structure"
```

---

## Task 2: 테스트 픽스처 (tests/conftest.py)

**Files:**
- Create: `tests/conftest.py`

테스트 전용 `codebase_test` AGE 그래프를 생성하고 소규모 노드/엣지를 적재. 세션 종료 시 그래프 삭제.

- [ ] **Step 1: conftest.py 작성**

```python
import json
import pytest
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv

load_dotenv()

TEST_GRAPH = "codebase_test"
TEST_DSN   = os.environ["AGE_DSN"]

TEST_NODES = [
    {"id": "UserService",  "label": "UserService",  "file_type": "code",     "source_file": "/src/UserService.java",  "source_location": "L1",  "community": 0, "norm_label": "userservice"},
    {"id": "UserRepo",     "label": "UserRepo",     "file_type": "code",     "source_file": "/src/UserRepo.java",     "source_location": "L1",  "community": 0, "norm_label": "userrepo"},
    {"id": "Article",      "label": "Article",      "file_type": "code",     "source_file": "/src/Article.java",      "source_location": "L1",  "community": 1, "norm_label": "article"},
    {"id": "README",       "label": "README",       "file_type": "document", "source_file": "/README.md",             "source_location": "L1",  "community": 2, "norm_label": "readme"},
]
TEST_EDGES = [
    {"source": "UserService", "target": "UserRepo",  "relation": "calls",    "confidence": "EXTRACTED", "confidence_score": 0.95, "weight": 1.0},
    {"source": "UserService", "target": "Article",   "relation": "imports",  "confidence": "EXTRACTED", "confidence_score": 0.80, "weight": 1.0},
]


def _cs(v):
    if v is None:
        return ""
    return str(v).replace("\\", "\\\\").replace("'", "\\'")


def _setup_age(cur):
    cur.execute("LOAD 'age';")
    cur.execute("SET search_path = ag_catalog, '$user', public;")


@pytest.fixture(scope="session")
def age_conn():
    conn = psycopg2.connect(TEST_DSN)
    cur  = conn.cursor()

    conn.autocommit = True
    _setup_age(cur)

    # 그래프 생성 (이미 있으면 삭제 후 재생성)
    try:
        cur.execute(f"SELECT drop_graph('{TEST_GRAPH}', true);")
    except Exception:
        conn.rollback()
    cur.execute(f"SELECT create_graph('{TEST_GRAPH}');")

    conn.autocommit = False

    # 노드 삽입
    for node in TEST_NODES:
        label = {"code": "CodeNode", "document": "DocumentNode"}.get(node["file_type"], "Node")
        cur.execute(f"""
            SELECT * FROM cypher('{TEST_GRAPH}', $$
                CREATE (n:{label} {{
                    id:              '{_cs(node["id"])}',
                    label:           '{_cs(node["label"])}',
                    file_type:       '{_cs(node["file_type"])}',
                    source_file:     '{_cs(node["source_file"])}',
                    source_location: '{_cs(node["source_location"])}',
                    community:       {int(node["community"])},
                    norm_label:      '{_cs(node["norm_label"])}'
                }})
            $$) AS (result agtype)
        """)
    conn.commit()

    # 엣지 삽입
    for edge in TEST_EDGES:
        rtype = edge["relation"].upper()
        cur.execute(f"""
            SELECT * FROM cypher('{TEST_GRAPH}', $$
                MATCH (a {{id: '{_cs(edge["source"])}'}}),
                      (b {{id: '{_cs(edge["target"])}'}})
                CREATE (a)-[:{rtype} {{
                    confidence:       '{_cs(edge["confidence"])}',
                    confidence_score: {float(edge["confidence_score"])},
                    weight:           {float(edge["weight"])}
                }}]->(b)
            $$) AS (result agtype)
        """)
    conn.commit()

    yield conn

    # 정리
    conn.autocommit = True
    _setup_age(cur)
    try:
        cur.execute(f"SELECT drop_graph('{TEST_GRAPH}', true);")
    except Exception:
        pass
    conn.close()
```

- [ ] **Step 2: 픽스처 연결 테스트 (더미)**

```python
# tests/test_age_queries.py 첫 줄만 작성해서 fixture 확인
def test_fixture_alive(age_conn):
    assert age_conn is not None
```

- [ ] **Step 3: 테스트 실행 — fixture 동작 확인**

```bash
cd C:\workspace\Nexus
pip install -r requirements.txt
pytest tests/test_age_queries.py::test_fixture_alive -v
```

Expected: `PASSED`

- [ ] **Step 4: 커밋**

```bash
git add tests/conftest.py tests/__init__.py tests/test_age_queries.py
git commit -m "test: add AGE test fixture (codebase_test graph)"
```

---

## Task 3: core/age_queries.py (TDD)

**Files:**
- Create: `core/age_queries.py`
- Modify: `tests/test_age_queries.py`

- [ ] **Step 1: 전체 테스트 먼저 작성 (tests/test_age_queries.py)**

```python
import json
import pytest
import os
from dotenv import load_dotenv

load_dotenv()

TEST_GRAPH = "codebase_test"

# --- conftest.py의 age_conn 픽스처를 쓰기 위해 import
# (conftest.py는 pytest가 자동 로드)


def test_fixture_alive(age_conn):
    assert age_conn is not None


# core/age_queries를 import — Task 3 구현 전에는 FAIL
import importlib, sys


def get_q():
    """age_queries 모듈을 TEST_GRAPH로 초기화해서 반환."""
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
    # UserService는 2개 엣지를 가짐 — 최상위여야 함
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
    # README는 연결 없음 — None 또는 빈 리스트
    assert path is None or path == []


def test_keyword_search(age_conn):
    q = get_q()
    results = q.keyword_search(["user"], hops=1)
    ids = [n["id"] for n in results]
    assert "UserService" in ids
    assert "UserRepo" in ids  # 1-hop 이웃


def test_keyword_search_no_results(age_conn):
    q = get_q()
    results = q.keyword_search(["xyznotexist"], hops=1)
    assert results == []
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/test_age_queries.py -v --tb=short
```

Expected: `ImportError: No module named 'core.age_queries'` 또는 `ModuleNotFoundError`

- [ ] **Step 3: core/age_queries.py 구현**

```python
"""
core/age_queries.py
AGE 'codebase' 그래프 쿼리 공통 레이어.
ThreadedConnectionPool 사용. FastAPI sync 핸들러와 MCP server 양쪽에서 import.
"""
import json
import re
import psycopg2
from psycopg2.pool import ThreadedConnectionPool

_pool: ThreadedConnectionPool | None = None
_graph: str = "codebase"


def init(dsn: str, graph: str = "codebase", minconn: int = 2, maxconn: int = 10):
    """앱 시작 시 한 번 호출. 연결 풀 초기화."""
    global _pool, _graph
    _graph = graph
    _pool  = ThreadedConnectionPool(minconn, maxconn, dsn)


def close():
    """앱 종료 시 풀 반환."""
    if _pool:
        _pool.closeall()


def _get_conn():
    conn = _pool.getconn()
    cur  = conn.cursor()
    cur.execute("LOAD 'age';")
    cur.execute("SET search_path = ag_catalog, '$user', public;")
    conn.commit()
    return conn


def _put_conn(conn):
    _pool.putconn(conn)


def _cs(v) -> str:
    """Cypher 문자열 리터럴용 이스케이프."""
    if v is None:
        return ""
    return str(v).replace("\\", "\\\\").replace("'", "\\'")


def _parse(v) -> dict | str | int | None:
    """AGE agtype → Python 객체."""
    if v is None:
        return None
    s = re.sub(r'::\w+$', '', str(v).strip())
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return s


# ── 쿼리 함수 ─────────────────────────────────────────────


def get_node(node_id: str) -> dict | None:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (n {{id: '{_cs(node_id)}'}})
                RETURN properties(n)
            $$) AS (props agtype)
        """)
        row = cur.fetchone()
        return _parse(row[0]) if row else None
    finally:
        _put_conn(conn)


def get_neighbors(node_id: str, depth: int = 1) -> list[dict]:
    """노드의 이웃 반환. 각 항목: {"node": {...}, "relation": "CALLS", "edge_props": {...}}"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (n {{id: '{_cs(node_id)}'}})-[r]-(m)
                RETURN properties(m), type(r), properties(r)
            $$) AS (node agtype, rel_type agtype, rel_props agtype)
        """)
        rows = cur.fetchall()
        return [
            {
                "node":       _parse(r[0]),
                "relation":   _parse(r[1]),
                "edge_props": _parse(r[2]),
            }
            for r in rows
        ]
    finally:
        _put_conn(conn)


def get_community(community_id: int) -> list[dict]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (n {{community: {int(community_id)}}})
                RETURN properties(n)
            $$) AS (props agtype)
        """)
        return [_parse(r[0]) for r in cur.fetchall()]
    finally:
        _put_conn(conn)


def god_nodes(limit: int = 10) -> list[dict]:
    """연결도 높은 순 노드 목록."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (n)-[r]-()
                RETURN properties(n), count(r) AS degree
                ORDER BY degree DESC
                LIMIT {int(limit)}
            $$) AS (props agtype, degree agtype)
        """)
        results = []
        for row in cur.fetchall():
            node = _parse(row[0])
            if node:
                node["_degree"] = _parse(row[1])
                results.append(node)
        return results
    finally:
        _put_conn(conn)


def graph_stats() -> dict:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (n) RETURN count(n)
            $$) AS (cnt agtype)
        """)
        node_cnt = _parse(cur.fetchone()[0])

        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH ()-[r]->() RETURN count(r)
            $$) AS (cnt agtype)
        """)
        edge_cnt = _parse(cur.fetchone()[0])

        return {"nodes": int(node_cnt), "edges": int(edge_cnt), "graph": _graph}
    finally:
        _put_conn(conn)


def shortest_path(from_id: str, to_id: str) -> list[dict] | None:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH p = shortestPath(
                    (a {{id: '{_cs(from_id)}'}})-[*]-(b {{id: '{_cs(to_id)}'}})
                )
                RETURN [n IN nodes(p) | properties(n)] AS path_nodes
            $$) AS (path_nodes agtype)
        """)
        row = cur.fetchone()
        if not row:
            return None
        return _parse(row[0])
    finally:
        _put_conn(conn)


def keyword_search(keywords: list[str], hops: int = 2) -> list[dict]:
    """
    키워드 → norm_label CONTAINS 검색 → N-hop BFS 확장.
    결과: 시드 노드 먼저, 이웃 노드 뒤에. LIMIT 없음 — 토큰 예산 제어는 호출자 책임.
    주의: confidence_score/degree 기반 정렬은 AGE Cypher [*0..N] 패턴에서 지원 어려움.
          시드 노드를 먼저 반환하는 것으로 근사치 처리.
    """
    if not keywords:
        return []

    conditions = " OR ".join(
        f"n.norm_label CONTAINS '{_cs(kw.lower())}'" for kw in keywords
    )
    conn = _get_conn()
    try:
        cur = conn.cursor()

        # Step 1: 시드 노드 (직접 매칭)
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (n) WHERE {conditions}
                RETURN properties(n)
            $$) AS (props agtype)
        """)
        seed_rows = cur.fetchall()
        results = []
        seen = set()
        for row in seed_rows:
            node = _parse(row[0])
            if node and node.get("id") not in seen:
                seen.add(node["id"])
                results.append(node)

        # Step 2: N-hop 이웃 (시드 노드 제외)
        if hops > 0 and results:
            seed_ids = list(seen)
            seed_condition = " OR ".join(
                f"seed.id = '{_cs(sid)}'" for sid in seed_ids
            )
            cur.execute(f"""
                SELECT * FROM cypher('{_graph}', $$
                    MATCH (seed) WHERE {seed_condition}
                    MATCH (seed)-[*1..{int(hops)}]-(neighbor)
                    RETURN DISTINCT properties(neighbor)
                $$) AS (props agtype)
            """)
            for row in cur.fetchall():
                node = _parse(row[0])
                if node and node.get("id") not in seen:
                    seen.add(node["id"])
                    results.append(node)

        return results
    finally:
        _put_conn(conn)
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
pytest tests/test_age_queries.py -v
```

Expected: 모든 테스트 PASSED (test_fixture_alive 포함 10개)

- [ ] **Step 5: 커밋**

```bash
git add core/age_queries.py tests/test_age_queries.py
git commit -m "feat: core/age_queries.py — ThreadedConnectionPool + 7 query functions (TDD)"
```

---

## Task 4: FastAPI 앱 + 미들웨어 (api/main.py)

**Files:**
- Create: `api/main.py`

rebuild_flag와 API Key 의존성을 앱 레벨에서 관리.

- [ ] **Step 1: api/main.py 작성**

```python
import threading
import subprocess
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse

import config
import core.age_queries as q
from api.routes import graph as graph_router
from api.routes import rebuild as rebuild_router

# ── rebuild 상태 ─────────────────────────────────────────
_rebuild_lock = threading.Lock()
_rebuilding   = False


def is_rebuilding() -> bool:
    return _rebuilding


def set_rebuilding(v: bool):
    global _rebuilding
    _rebuilding = v


# ── API Key 의존성 ─────────────────────────────────────────
def verify_api_key(x_api_key: str = Header(default="")):
    if config.API_KEY and x_api_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Lifespan ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    q.init(config.AGE_DSN, config.AGE_GRAPH)
    yield
    q.close()


# ── 앱 ───────────────────────────────────────────────────
app = FastAPI(title="Nexus", lifespan=lifespan)


@app.middleware("http")
async def rebuild_guard(request: Request, call_next):
    """rebuild 중에는 /query, /node 등 읽기 요청 503 반환."""
    if _rebuilding and request.url.path not in ("/rebuild", "/docs", "/openapi.json"):
        return JSONResponse(status_code=503, content={"detail": "Rebuild in progress"})
    return await call_next(request)


app.include_router(graph_router.router,   dependencies=[Depends(verify_api_key)])
app.include_router(rebuild_router.router, dependencies=[Depends(verify_api_key)])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=config.API_PORT, reload=False)
```

- [ ] **Step 2: 임포트 오류 없는지 확인**

```bash
python -c "import api.main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add api/main.py
git commit -m "feat: FastAPI app with API key auth and rebuild guard middleware"
```

---

## Task 5: 그래프 라우트 (api/routes/graph.py) — TDD

**Files:**
- Create: `api/routes/graph.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: 테스트 먼저 작성 (tests/test_api.py)**

```python
import os
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()
os.environ["AGE_GRAPH"] = "codebase_test"   # 테스트 그래프 사용

from api.main import app
import core.age_queries as q

TEST_KEY = os.getenv("API_KEY", "")

@pytest.fixture(scope="module", autouse=True)
def init_pool(age_conn):
    """conftest의 age_conn이 테스트 그래프를 셋업한 뒤 풀 초기화."""
    q.init(os.environ["AGE_DSN"], "codebase_test")
    yield
    q.close()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def h():
    return {"X-Api-Key": TEST_KEY} if TEST_KEY else {}


def test_get_node_found(client):
    r = client.get("/node/UserService", headers=h())
    assert r.status_code == 200
    assert r.json()["id"] == "UserService"


def test_get_node_missing(client):
    r = client.get("/node/NOPE_MISSING", headers=h())
    assert r.status_code == 404


def test_get_neighbors(client):
    r = client.get("/neighbors/UserService", headers=h())
    assert r.status_code == 200
    ids = [n["node"]["id"] for n in r.json()]
    assert "UserRepo" in ids


def test_get_community(client):
    r = client.get("/community/0", headers=h())
    assert r.status_code == 200
    ids = [n["id"] for n in r.json()]
    assert "UserService" in ids


def test_god_nodes(client):
    r = client.get("/god-nodes?limit=3", headers=h())
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_graph_stats(client):
    r = client.get("/stats", headers=h())
    assert r.status_code == 200
    data = r.json()
    assert data["nodes"] >= 4
    assert data["edges"] >= 2


def test_shortest_path_found(client):
    r = client.get("/path?from_id=UserService&to_id=Article", headers=h())
    assert r.status_code == 200


def test_query_endpoint(client):
    r = client.post("/query", json={"keywords": ["user"], "hops": 1}, headers=h())
    assert r.status_code == 200
    ids = [n["id"] for n in r.json()]
    assert "UserService" in ids


def test_auth_rejected(client):
    r = client.get("/stats", headers={"X-Api-Key": "wrong-key"})
    if TEST_KEY:
        assert r.status_code == 401


def test_no_auth_without_key_set(client):
    """API_KEY가 빈 문자열이면 키 없이도 통과."""
    if not TEST_KEY:
        r = client.get("/stats")
        assert r.status_code == 200
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/test_api.py -v --tb=short
```

Expected: `ImportError` 또는 `404` (라우트 없음)

- [ ] **Step 3: api/routes/graph.py 구현**

```python
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import core.age_queries as q

router = APIRouter()


class QueryRequest(BaseModel):
    keywords: list[str]
    hops: int = 2


@router.get("/node/{node_id}")
def get_node(node_id: str):
    node = q.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.get("/neighbors/{node_id}")
def get_neighbors(node_id: str, depth: int = Query(default=1, ge=1, le=5)):
    return q.get_neighbors(node_id, depth=depth)


@router.get("/community/{community_id}")
def get_community(community_id: int):
    return q.get_community(community_id)


@router.get("/god-nodes")
def god_nodes(limit: int = Query(default=10, ge=1, le=100)):
    return q.god_nodes(limit=limit)


@router.get("/stats")
def graph_stats():
    return q.graph_stats()


@router.get("/path")
def shortest_path(from_id: str, to_id: str):
    path = q.shortest_path(from_id, to_id)
    if path is None:
        raise HTTPException(status_code=404, detail="No path found")
    return {"path": path}


@router.post("/query")
def query_graph(req: QueryRequest):
    return q.keyword_search(req.keywords, hops=req.hops)
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
pytest tests/test_api.py -v
```

Expected: 모든 테스트 PASSED

- [ ] **Step 5: 커밋**

```bash
git add api/routes/graph.py tests/test_api.py
git commit -m "feat: graph routes /node /neighbors /community /god-nodes /stats /path /query (TDD)"
```

---

## Task 6: Rebuild 라우트 (api/routes/rebuild.py) — TDD

**Files:**
- Create: `api/routes/rebuild.py`
- Create: `tests/test_rebuild.py`

- [ ] **Step 1: 테스트 먼저 작성 (tests/test_rebuild.py)**

```python
import os
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()
os.environ["AGE_GRAPH"] = "codebase_test"

import api.main as main_module
from api.main import app
import core.age_queries as q

TEST_KEY = os.getenv("API_KEY", "")


@pytest.fixture(scope="module", autouse=True)
def init_pool(age_conn):
    q.init(os.environ["AGE_DSN"], "codebase_test")
    yield
    q.close()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def h():
    return {"X-Api-Key": TEST_KEY} if TEST_KEY else {}


def test_503_during_rebuild(client):
    """rebuild_flag=True면 /stats가 503 반환."""
    main_module.set_rebuilding(True)
    try:
        r = client.get("/stats", headers=h())
        assert r.status_code == 503
        assert "Rebuild" in r.json()["detail"]
    finally:
        main_module.set_rebuilding(False)


def test_rebuild_endpoint_already_running(client, monkeypatch):
    """이미 rebuild 중이면 409 반환."""
    main_module.set_rebuilding(True)
    try:
        r = client.post("/rebuild", headers=h())
        assert r.status_code == 409
    finally:
        main_module.set_rebuilding(False)


def test_stats_available_after_rebuild(client):
    """rebuild 완료 후 /stats 정상 동작."""
    main_module.set_rebuilding(False)
    r = client.get("/stats", headers=h())
    assert r.status_code == 200
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/test_rebuild.py -v --tb=short
```

Expected: `ImportError` 또는 `404` (rebuild 라우트 없음)

- [ ] **Step 3: api/routes/rebuild.py 구현**

```python
import subprocess
import threading
from fastapi import APIRouter, HTTPException, BackgroundTasks

import config
import api.main as main_module
from loader.age_loader import run_loader

router = APIRouter()


def _do_rebuild():
    try:
        main_module.set_rebuilding(True)

        # Step 1: graphify 실행
        subprocess.run(
            [config.GRAPHIFY_PATH, "--update", config.SOURCE_DIR],
            check=True,
            capture_output=True,
        )

        # Step 2: 로더 실행
        run_loader(config.AGE_DSN, config.GRAPH_OUTPUT_PATH, config.AGE_GRAPH)

    finally:
        main_module.set_rebuilding(False)


@router.post("/rebuild", status_code=202)
def trigger_rebuild(background_tasks: BackgroundTasks):
    if main_module.is_rebuilding():
        raise HTTPException(status_code=409, detail="Rebuild already in progress")

    background_tasks.add_task(_do_rebuild)
    return {"status": "accepted", "message": "Rebuild started in background"}
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
pytest tests/test_rebuild.py -v
```

Expected: 모든 테스트 PASSED

- [ ] **Step 5: 커밋**

```bash
git add api/routes/rebuild.py tests/test_rebuild.py
git commit -m "feat: /rebuild endpoint with 503 guard and 409 on double-trigger (TDD)"
```

---

## Task 7: Loader 이전 (loader/age_loader.py)

**Files:**
- Create: `loader/age_loader.py`

`graphify_age_loader.py`의 로직을 Nexus로 이전. `run_loader()` 함수를 public API로 추가해 rebuild 라우트에서 호출 가능하게.

- [ ] **Step 1: loader/age_loader.py 작성**

기존 `graphify_age_loader.py`의 전체 내용을 복사하되 다음 변경사항 적용:
1. `main()` 함수는 그대로 유지 (CLI 실행용)
2. `run_loader(dsn, graph_path, graph_name)` 함수 추가 — rebuild 라우트에서 호출

```python
# loader/age_loader.py 하단에 추가할 함수:

def run_loader(dsn: str, graph_path: str = "graphify-out/graph.json", graph_name: str = "codebase"):
    """rebuild 라우트에서 프로그래매틱 호출용."""
    import psycopg2
    import json

    with open(graph_path, encoding="utf-8") as f:
        data = json.load(f)

    nodes      = data.get("nodes", [])
    edges      = data.get("links", [])
    hyperedges = data.get("graph", {}).get("hyperedges", [])

    conn = psycopg2.connect(dsn)
    cur  = conn.cursor()

    conn.autocommit = True
    setup_age(cur)
    conn.autocommit = False

    clear_graph(conn, cur, graph_name)
    insert_nodes(conn, cur, nodes, graph_name)
    insert_edges(conn, cur, edges, graph_name)
    if hyperedges:
        insert_hyperedges(conn, cur, hyperedges, graph_name)

    print_stats(cur, graph_name)
    conn.close()
```

- [ ] **Step 2: 임포트 확인**

```bash
python -c "from loader.age_loader import run_loader; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add loader/age_loader.py
git commit -m "feat: loader/age_loader.py — ported from graphify_age_loader.py, added run_loader()"
```

---

## Task 8: MCP SSE 서버 (nexus_mcp/server.py)

**Files:**
- Create: `nexus_mcp/server.py`

`mcp` Python SDK SSE transport. `core/age_queries.py` 함수를 MCP 툴로 노출.

- [ ] **Step 1: nexus_mcp/server.py 작성**

```python
"""
nexus_mcp/server.py
Nexus MCP SSE 서버. Claude Code IDE 및 범용챗봇 컨테이너에서 접근.
실행: python nexus_mcp/server.py
포트: MCP_PORT (기본 8006)
디렉토리명 nexus_mcp/ 사용 이유: 'mcp/'로 지으면 설치된 mcp 패키지를 shadowing해 import 실패.
"""
import json
import sys
import os

# 루트 경로를 sys.path에 추가 (standalone 실행 시)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from starlette.applications import Starlette
from starlette.routing import Route, Mount
import uvicorn

import config
import core.age_queries as q

# ── 풀 초기화 ─────────────────────────────────────────────
q.init(config.AGE_DSN, config.AGE_GRAPH)

# ── MCP 서버 ─────────────────────────────────────────────
server = Server("nexus-graph")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="get_node",        description="노드 상세 정보 조회",         inputSchema={"type":"object","properties":{"id":{"type":"string"}},"required":["id"]}),
        Tool(name="get_neighbors",   description="노드의 직접 연결 이웃 조회",    inputSchema={"type":"object","properties":{"id":{"type":"string"},"depth":{"type":"integer","default":1}},"required":["id"]}),
        Tool(name="get_community",   description="커뮤니티 멤버 노드 목록",       inputSchema={"type":"object","properties":{"community_id":{"type":"integer"}},"required":["community_id"]}),
        Tool(name="god_nodes",       description="최고 연결도 노드 목록",         inputSchema={"type":"object","properties":{"limit":{"type":"integer","default":10}}}),
        Tool(name="graph_stats",     description="그래프 기본 통계",              inputSchema={"type":"object","properties":{}}),
        Tool(name="shortest_path",   description="두 노드 간 최단 경로",          inputSchema={"type":"object","properties":{"from_id":{"type":"string"},"to_id":{"type":"string"}},"required":["from_id","to_id"]}),
        Tool(name="query_graph",     description="키워드 배열로 BFS 탐색",        inputSchema={"type":"object","properties":{"keywords":{"type":"array","items":{"type":"string"}},"hops":{"type":"integer","default":2}},"required":["keywords"]}),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_node":
        result = q.get_node(arguments["id"])
    elif name == "get_neighbors":
        result = q.get_neighbors(arguments["id"], depth=arguments.get("depth", 1))
    elif name == "get_community":
        result = q.get_community(int(arguments["community_id"]))
    elif name == "god_nodes":
        result = q.god_nodes(limit=int(arguments.get("limit", 10)))
    elif name == "graph_stats":
        result = q.graph_stats()
    elif name == "shortest_path":
        result = q.shortest_path(arguments["from_id"], arguments["to_id"])
    elif name == "query_graph":
        result = q.keyword_search(arguments["keywords"], hops=int(arguments.get("hops", 2)))
    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


# ── SSE 앱 ────────────────────────────────────────────────
transport = SseServerTransport("/messages/")


async def handle_sse(request):
    async with transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await server.run(*streams, server.create_initialization_options())


starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=transport.handle_post_message),
    ]
)


if __name__ == "__main__":
    uvicorn.run(starlette_app, host="0.0.0.0", port=config.MCP_PORT)
```

- [ ] **Step 2: 임포트 확인**

```bash
python -c "import nexus_mcp.server as s; print('OK')"
```

Expected: `OK` (실제 서버 시작 없이 import만)

- [ ] **Step 3: 커밋**

```bash
git add nexus_mcp/__init__.py nexus_mcp/server.py
git commit -m "feat: MCP SSE server (port 8006) — 7 tools wrapping core/age_queries.py"
```

---

## Task 9: .mcp.json 업데이트 + AGE Viewer 배포

**Files:**
- Modify: `C:\workspace\spring-boot-realworld-example-app\.mcp.json` (또는 `~/.claude/claude_desktop_config.json`)

- [ ] **Step 1: .mcp.json에 Nexus MCP 서버 등록**

현재 `.mcp.json`을 열고 graphify MCP 서버 엔트리를 Nexus SSE 방식으로 교체:

```json
{
  "mcpServers": {
    "nexus-graph": {
      "type": "sse",
      "url": "http://193.168.195.222:8006/sse"
    }
  }
}
```

로컬에서 Nexus를 실행할 경우:
```json
{
  "mcpServers": {
    "nexus-graph": {
      "type": "sse",
      "url": "http://localhost:8006/sse"
    }
  }
}
```

- [ ] **Step 2: AGE Viewer Docker 실행 (Hostinger 서버에서)**

```bash
# Hostinger 서버 SSH 접속 후:
docker run -d --name age-viewer \
  -p 8005:3000 \
  apache/age-viewer

# 실행 확인
docker ps | grep age-viewer
```

브라우저에서 `http://193.168.195.222:8005` 접속.
연결 정보 입력:
- Host: `193.168.195.222`
- Port: `5434`
- Database: `lightrag`
- User: `postgres`

> AGE Viewer 내부 포트가 3000이 아닐 경우: `docker logs age-viewer`에서 포트 확인 후 `-p 8005:<실제포트>`로 수정.

- [ ] **Step 3: Nexus 서비스 직접 설치 (Hostinger 서버에서)**

```bash
# Hostinger 서버 SSH 접속 후:
git clone <nexus-repo-url> /opt/nexus
cd /opt/nexus
pip install -r requirements.txt

# .env 작성
cp .env.example .env
nano .env  # AGE_DSN, API_KEY 등 실제 값 입력

# 두 프로세스 백그라운드 실행
nohup python api/main.py > /var/log/nexus-api.log 2>&1 &
nohup python nexus_mcp/server.py > /var/log/nexus-mcp.log 2>&1 &
```

- [ ] **Step 4: 동작 확인**

```bash
# REST API
curl -H "X-Api-Key: <your-key>" http://193.168.195.222:8004/stats

# Expected:
# {"nodes": 603, "edges": 1034, "graph": "codebase"}
```

- [ ] **Step 5: 최종 커밋**

```bash
cd C:\workspace\Nexus
git add .
git commit -m "docs: .env.example, deployment instructions"
```

---

## 전체 테스트 실행

```bash
cd C:\workspace\Nexus
pytest tests/ -v
```

Expected: 모든 테스트 PASSED (test_age_queries + test_api + test_rebuild)

---

## NOT in scope

- Router/오케스트레이터 (LightRAG + Nexus 결합) — 별도 작업
- Loader MERGE (증분 업데이트) — 고빈도 rebuild 필요 시
- Docker화 — 서비스 안정화 후
- 코드 노드 임베딩 — 코드 유사도 검색 필요 시

## What already exists

- `graphify_age_loader.py` (spring-boot-realworld): Task 7에서 loader/age_loader.py로 이전. 원본은 POC 참조용 유지.
- `graphify_mcp_server.py` (spring-boot-realworld): graph.json 기반. Task 9에서 .mcp.json을 Nexus SSE로 교체하면 대체됨.
- AGE 'codebase' 그래프: 이미 Hostinger에 존재. loader 재실행 불필요.
