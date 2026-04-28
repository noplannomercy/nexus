# Nexus 서비스 설계 스펙

> 작성일: 2026-04-28  
> 상태: 초안 (ENG-REVIEW 전)

---

## 1. 목적 및 범위

Nexus는 graphify가 생성한 코드베이스 지식그래프를 Apache AGE에 적재하고, 두 가지 인터페이스(REST API, MCP SSE 서버)로 서빙하는 독립 서비스다.

**이번 구현 범위:**
- `core/age_queries.py` — 공통 AGE Cypher 쿼리 레이어
- FastAPI REST API (포트 8004) — Router/오케스트레이터 HTTP 호출 인터페이스
- MCP SSE 서버 (포트 8006) — Claude Code IDE + 범용챗봇 컨테이너 인터페이스
- `loader/age_loader.py` — graphify_age_loader.py 이전 및 정리
- AGE Viewer 배포 (포트 8005, Docker)

**범위 외:**
- Router/오케스트레이터 구현
- LightRAG 연동
- Loader MERGE 업그레이드 (현재: full wipe + CREATE)
- 코드 노드 임베딩

---

## 2. 아키텍처

### 2-1. 전체 구성

```
Nexus 서비스 (Hostinger)
  ├── FastAPI REST API     :8004  ← Router/오케스트레이터
  └── MCP SSE 서버         :8006  ← Claude Code IDE, 범용챗봇 컨테이너
  둘 다 → core/age_queries.py → PostgreSQL AGE 'codebase' (:5434)

AGE Viewer (Docker)        :8005  ← 사람이 직접 그래프 탐색
```

### 2-2. 공통 쿼리 레이어

`core/age_queries.py` 하나가 모든 쿼리 로직을 담는다. REST API와 MCP 서버 모두 이 모듈을 import해서 사용. DB 연결 풀도 여기서 관리.

```
core/age_queries.py
  get_node(id)
  get_neighbors(id, depth)
  get_community(community_id)
  god_nodes(limit)
  graph_stats()
  shortest_path(from_id, to_id)
  keyword_search(keywords, hops)   ← /query BFS/DFS 핵심
```

### 2-3. 프로젝트 구조

```
Nexus/
├── core/
│   └── age_queries.py
├── api/
│   ├── main.py
│   └── routes/
│       ├── graph.py        ← /node, /neighbors, /community, /god-nodes, /stats, /path
│       └── rebuild.py      ← /rebuild
├── mcp/
│   └── server.py           ← MCP SSE 서버 (mcp 라이브러리)
├── loader/
│   └── age_loader.py       ← graphify_age_loader.py 이전
├── docs/
│   └── architecture.md
├── config.py               ← 환경변수 (DSN, graph name, ports)
└── requirements.txt
```

---

## 3. REST API 엔드포인트

| Method | Path | 설명 | 핵심 파라미터 |
|--------|------|------|--------------|
| POST | `/query` | 키워드 배열 → BFS/DFS 탐색 | `keywords: list[str]`, `hops: int = 2` |
| GET | `/node/{id}` | 노드 상세 정보 | `id` |
| GET | `/neighbors/{id}` | 직접 연결 이웃 | `id`, `depth: int = 1` |
| GET | `/community/{id}` | 커뮤니티 멤버 목록 | `community_id` |
| GET | `/god-nodes` | 최고 연결도 노드 | `limit: int = 10` |
| GET | `/stats` | 그래프 기본 통계 | — |
| GET | `/path` | 두 노드 간 최단 경로 | `from`, `to` |
| POST | `/rebuild` | 리빌드 실행 | — |

**`/query` 설계 결정:** 키워드 추출은 호출자(Router/오케스트레이터) 책임. Nexus는 `keywords` 배열을 받아 AGE에서 `norm_label` CONTAINS 검색 후 N-hop BFS 확장만 수행. LLM 의존성 없음.

---

## 4. MCP 서버

`mcp` Python 라이브러리 SSE transport 사용. `core/age_queries.py` 함수들을 MCP 툴로 노출.

**툴 목록 (현재 MCP 서버와 동일한 인터페이스 유지):**
- `get_node`, `get_neighbors`, `get_community`
- `god_nodes`, `graph_stats`, `shortest_path`
- `query_graph(keywords: list[str], hops: int = 2)` — REST `/query`와 동일한 시그니처. 키워드 추출은 호출자 책임.

**접근 방법:**
- Claude Code: `.mcp.json`에 SSE URL `http://localhost:8006/sse` 등록 (로컬 실행 시) 또는 `http://193.168.195.222:8006/sse` (원격)
- 범용챗봇 컨테이너: 내부 네트워크 호스트명으로 접근

---

## 5. Rebuild 메커니즘

```
POST /rebuild
  → rebuild_flag = True (메모리)
  → graphify --update 실행 (subprocess)
  → age_loader.py 실행
  → rebuild_flag = False

rebuild_flag = True 중
  → 모든 /query, /node 등 → 503 Service Unavailable
```

**스케줄:** 외부 cron (서버 crontab) → `POST /rebuild`. Nexus 내부 스케줄러 없음.  
**동시 실행 방지:** rebuild_flag 체크로 중복 요청 거부.  
**전제조건:** graphify가 Hostinger 서버에 설치돼 있어야 함 (`pip install graphify` 또는 소스 설치).

---

## 6. AGE Viewer

```bash
docker run -d --name age-viewer \
  -p 8005:3000 \
  apache/age-viewer
```

별도 Docker 컨테이너. Nexus 서비스와 독립. lightrag PostgreSQL (포트 5434)에 직접 연결.

---

## 7. 설정 (config.py)

| 키 | 기본값 | 설명 |
|----|--------|------|
| `AGE_DSN` | — | `postgresql://postgres:pass@host:5434/lightrag` |
| `AGE_GRAPH` | `codebase` | AGE 그래프 이름 |
| `API_PORT` | `8004` | REST API 포트 |
| `MCP_PORT` | `8006` | MCP SSE 포트 |

환경변수 또는 `.env` 파일로 주입.

---

## 8. 배포

**1단계: 직접 설치 (현재)**
```bash
git clone <repo> Nexus
cd Nexus
pip install -r requirements.txt
# .env 파일 작성
python api/main.py      # 포트 8004
python mcp/server.py    # 포트 8006
```

**2단계: Docker화 (이후)**
- 단일 Dockerfile, supervisord로 두 프로세스 관리
- docker-compose로 LightRAG 옆에 배치

---

## 9. 의존성

- `fastapi`, `uvicorn`
- `psycopg2-binary`
- `mcp` (Anthropic MCP Python SDK)
- `python-dotenv`

---

## 10. 알려진 한계 (이번 구현)

| 항목 | 현황 | 개선 시점 |
|------|------|---------|
| Loader MERGE | full wipe + CREATE | 고빈도 rebuild 필요 시 |
| rebuild_flag | 메모리, 재시작 시 초기화 | 안정성 필요 시 DB 플래그로 |
| 코드 노드 임베딩 | 없음 | 코드 유사도 검색 필요 시 |
