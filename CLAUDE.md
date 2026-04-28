# 작업 시작 전

스펙: `docs/superpowers/specs/2026-04-28-nexus-design.md`
플랜: `docs/superpowers/plans/2026-04-28-nexus-implementation.md`
플랜을 읽고 현재 체크박스 상태를 확인한 뒤 작업을 시작한다.

---

# 개요

graphify 코드베이스 지식그래프를 AGE에서 서빙하는 독립 서비스.
FastAPI REST API(포트 8004) + MCP SSE 서버(포트 8006)가 공통 쿼리 레이어를 공유.

---

# 제약 사항

- **`nexus_mcp/`** — MCP 서버 디렉토리는 반드시 `nexus_mcp/`여야 한다. `mcp/`로 만들면 설치된 `mcp` 패키지를 shadowing해 import가 깨진다.
- **sync FastAPI 핸들러** — 모든 route 함수는 `async def` 없이 작성한다. FastAPI가 자동 스레드풀 실행. `async def`로 쓰면 psycopg2가 이벤트 루프를 블로킹한다.
- **AGE 세션 초기화** — `ThreadedConnectionPool`에서 꺼낸 연결마다 `LOAD 'age'`와 `SET search_path`를 실행해야 한다. `_get_conn()` 안에서 처리.
- **테스트는 실제 AGE DB** — `codebase_test` 그래프 사용. 모킹 없음. AGE 호환성 문제를 놓친다.
- **keyword_search LIMIT 없음** — 전체 반환, 토큰 예산 제어는 Router 책임.

---

# 준수 사항

1. Cypher 문자열 임베딩은 반드시 `_cs()` 함수로 이스케이프한다 (`\` → `\\`, `'` → `\'`).
2. 쿼리 함수에서 연결을 얻으면 `finally` 블록에서 반드시 `_put_conn(conn)`으로 반환한다.
3. API 응답에 `async def`가 없는 동기 핸들러만 사용한다.
4. `config.py`의 환경변수를 직접 import해서 쓴다. hardcode 금지.
5. 테스트는 `codebase_test` 그래프를 사용하며, `conftest.py`의 `age_conn` 픽스처에 의존한다.

---

# 스택

| 레이어 | 기술 |
|--------|------|
| DB | PostgreSQL + Apache AGE 1.6.0 (포트 5434) |
| DB 드라이버 | psycopg2-binary, ThreadedConnectionPool |
| REST API | FastAPI + uvicorn (포트 8004) |
| MCP 서버 | mcp SDK SSE transport + starlette (포트 8006) |
| 테스트 | pytest + httpx (FastAPI TestClient) |

---

# 구조

| 경로 | 역할 |
|------|------|
| `config.py` | 모든 환경변수 (AGE_DSN, API_KEY, 포트, 경로) |
| `core/age_queries.py` | ThreadedConnectionPool + 7 쿼리 함수 — 공통 레이어 |
| `api/main.py` | FastAPI 앱, rebuild_flag, API Key 미들웨어 |
| `api/routes/graph.py` | /query /node /neighbors /community /god-nodes /stats /path |
| `api/routes/rebuild.py` | /rebuild (백그라운드 태스크) |
| `nexus_mcp/server.py` | MCP SSE 서버 — core/age_queries.py 래핑 |
| `loader/age_loader.py` | graph.json → AGE 적재 (graphify_age_loader.py 이전) |
| `tests/conftest.py` | codebase_test 그래프 픽스처 |

---

# 하네스 진화 원칙

실패나 제약을 새로 발견하면 제약 사항에 추가한다. 커밋 전 자문: "CLAUDE.md 업데이트 필요한가?"

---

# 완료 조건

```bash
pytest tests/ -v        # 전체 PASS
curl -H "X-Api-Key: $API_KEY" http://localhost:8004/stats   # {"nodes": N, "edges": M, ...}
```
