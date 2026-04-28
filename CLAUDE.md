# 작업 시작 전

**상태: 구현 완료 (2026-04-28)**
GitHub: https://github.com/noplannomercy/nexus
테스트: 25/25 PASS

추가 작업 시 제약 사항과 하네스 진화 원칙 반드시 확인.

---

# 개요

graphify 코드베이스 지식그래프를 AGE에서 서빙하는 독립 서비스.
FastAPI REST API(포트 8004) + MCP SSE 서버(포트 8006)가 공통 쿼리 레이어를 공유.
HCA RAG 3-스토어 아키텍처에서 코드베이스 담당 스토어.

---

# 제약 사항

- **`nexus_mcp/`** — MCP 서버 디렉토리는 반드시 `nexus_mcp/`여야 한다. `mcp/`로 만들면 설치된 `mcp` 패키지를 shadowing해 import가 깨진다.
- **sync FastAPI 핸들러** — 모든 route 함수는 `async def` 없이 작성한다. FastAPI가 자동 스레드풀 실행. `async def`로 쓰면 psycopg2가 이벤트 루프를 블로킹한다.
- **AGE 세션 초기화** — `ThreadedConnectionPool`에서 꺼낸 연결마다 `LOAD 'age'`와 `SET search_path`를 실행해야 한다. `_get_conn()` 안에서 처리.
- **테스트는 실제 AGE DB** — `codebase_test` 그래프 사용. 모킹 없음. AGE 호환성 문제를 놓친다.
- **keyword_search LIMIT 없음** — 전체 반환, 토큰 예산 제어는 Router 책임.
- **shortestPath() 미지원** — AGE 1.6.0은 `shortestPath()` 함수 없음. 변수 길이 경로 `[*1..15]->` + `LIMIT 1`로 대체.
- **rebuild는 서빙 전용** — Nexus는 graph.json을 받아서 AGE에 올리는 역할만. graphify 실행(소스 분석)은 Nexus 밖에서 처리.
- **keyword_search N+1 금지** — 씨드별 개별 쿼리 금지. IN 리스트로 단일 쿼리 확장.
- **rebuild 중 503** — `rebuild_flag`로 제어. 미들웨어에서 `raise HTTPException` 금지, `JSONResponse` 직접 반환해야 함.

---

# 준수 사항

1. Cypher 문자열 임베딩은 반드시 `_cs()` 함수로 이스케이프한다.
2. 쿼리 함수에서 연결을 얻으면 `finally` 블록에서 반드시 `_put_conn(conn)`으로 반환한다.
3. node_id 입력은 `_resolve_id()`로 퍼지 해소 후 사용한다 (`get_node`, `get_neighbors`, `shortest_path`).
4. `config.py`의 환경변수를 직접 import해서 쓴다. hardcode 금지.
5. 테스트는 `codebase_test` 그래프를 사용하며, `conftest.py`의 `age_conn` 픽스처에 의존한다.

---

# 스택

| 레이어 | 기술 |
|--------|------|
| DB | PostgreSQL 16 + Apache AGE 1.6.0 (포트 5434, Hostinger 193.168.195.222) |
| DB 드라이버 | psycopg2-binary, ThreadedConnectionPool |
| REST API | FastAPI + uvicorn (포트 8004) |
| MCP 서버 | mcp SDK 1.6.0 SSE transport + starlette (포트 8006) |
| 테스트 | pytest + FastAPI TestClient |

---

# 구조

| 경로 | 역할 |
|------|------|
| `config.py` | 환경변수 (AGE_DSN, API_KEY, 포트, 경로) |
| `core/age_queries.py` | ThreadedConnectionPool + `_resolve_id` + 7 쿼리 함수 |
| `api/main.py` | FastAPI 앱, rebuild_flag, API Key 미들웨어 |
| `api/routes/graph.py` | GET node/neighbors/community/god-nodes/stats/path, POST search |
| `api/routes/rebuild.py` | POST /rebuild/ (백그라운드 스레드) |
| `nexus_mcp/server.py` | MCP SSE 서버 — core/age_queries.py 래핑, 7개 툴 |
| `loader/age_loader.py` | graph.json → AGE 적재 |
| `tests/conftest.py` | codebase_test 그래프 픽스처 (4노드 2엣지) |
| `run_api.py` | REST API 진입점 |
| `run_mcp.py` | MCP 서버 진입점 |

---

# 하네스 진화 원칙

실패나 제약을 새로 발견하면 제약 사항에 추가한다. 커밋 전 자문: "CLAUDE.md 업데이트 필요한가?"

---

# 완료 조건

```bash
pytest tests/ -v                          # 25/25 PASS
curl http://localhost:8004/health         # {"status": "ok"}
curl http://localhost:8004/graph/stats    # {"nodes": N, "edges": M}
curl http://localhost:8006/sse            # event: endpoint
```
