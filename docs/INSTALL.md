# Nexus 설치 매뉴얼

> 포트: 8005(REST API), 8006(MCP SSE) | 역할: graphify 출력물(graph.json)을 AGE 그래프 DB에 서빙

---

## 1. 사전 조건

- Docker, Docker Compose 설치
- PostgreSQL + AGE 확장 설치된 DB 접근 가능 (Hostinger DB)

---

## 2. 설치

```bash
# 1. 클론
git clone https://github.com/noplannomercy/Nexus.git
cd Nexus

# 2. 환경변수 설정
cp .env.example .env
vi .env
```

### .env 필수 항목

| 변수 | 설명 | 예시 |
|------|------|------|
| `AGE_DSN` | PostgreSQL+AGE DSN | `postgresql://postgres:pass@host:5434/lightrag` |
| `AGE_GRAPH` | AGE 그래프 이름 | `codebase` |
| `API_PORT` | REST API 포트 | `8005` |
| `MCP_PORT` | MCP SSE 포트 | `8006` |
| `API_KEY` | API 인증 키 | `change-me-secret-key` |
| `GRAPHIFY_PATH` | graphify 바이너리 경로 | `/usr/local/bin/graphify` |
| `SOURCE_DIR` | 소스 코드 디렉토리 | `/opt/hca-legacy` |
| `GRAPH_OUTPUT_PATH` | graph.json 출력 경로 | `graphify-out/graph.json` |

```bash
# 3. 빌드 + 기동 (API + MCP 동시 기동)
docker compose up -d --build

# 4. 헬스체크
curl http://localhost:8005/health
# 예상: {"status":"ok"}
```

> `nexus-api`(8005)와 `nexus-mcp`(8006) 두 컨테이너가 같은 이미지로 기동됨.

---

## 3. MCP 클라이언트 연결 (.mcp.json)

```json
{
  "nexus": {
    "type": "sse",
    "url": "http://<서버IP>:8006/sse"
  }
}
```

---

## 4. 주요 명령어

```bash
# 로그 확인
docker compose logs -f nexus-api
docker compose logs -f nexus-mcp

# 재시작
docker compose restart

# 재빌드 후 교체
docker compose up -d --build

# 정지
docker compose down
```

---

## 5. 트러블슈팅

| 증상 | 원인 | 조치 |
|------|------|------|
| AGE 연결 실패 | DSN 오류 또는 AGE 확장 미설치 | `AGE_DSN` 확인, `CREATE EXTENSION age` 실행 |
| MCP SSE 연결 안됨 | nexus-mcp 컨테이너 미기동 | `docker compose logs nexus-mcp` 확인 |
| 그래프 데이터 없음 | graph.json 미로드 | graphify 실행 후 REST API로 로드 필요 |
