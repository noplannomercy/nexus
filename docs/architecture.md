# Nexus — 아키텍처 문서

> 작성일: 2026-04-28
> 목적: HCA 레거시 코드베이스 지식그래프 서비스

---

## 1. 개요

Nexus는 graphify가 생성한 코드베이스 지식그래프를 Apache AGE에 적재하고, REST API로 서빙하는 독립 서비스다. HCA RAG 시스템의 3-스토어 분리 아키텍처에서 **코드베이스 스토어** 역할을 담당한다.

---

## 2. 전체 RAG 시스템 아키텍처

```
사용자 질문
    ↓
Router (Open WebUI 또는 LightRAG pipeline)
  ├── LightRAG API    → 비정형 문서 컨텍스트  (질문 유형에 따라 선택)
  └── Nexus REST API  → 코드 구조 컨텍스트   (질문 유형에 따라 선택)
    ↓
필요 시 양쪽 결합 (토큰 예산 상한 적용)
    ↓
Agent (LLM) → 최종 답변
```

### 3-스토어 분리 전략

| 스토어 | 담당 | 도구 |
|--------|------|------|
| 코드베이스 | Java/스크립트 구조, 클래스 관계 | graphify → **Nexus** → AGE |
| Oracle 패키지 | 패키지/SP 의존성 | 역문서 엔진 → AGE |
| 일반 문서 | 비정형 문서 의미 검색 | LightRAG → pgvector + AGE |

**분리 이유:** 지식 도메인별 특성이 근본적으로 다름. 하나로 합치면 전용 툴 강점 희석.

---

## 3. Nexus 서비스 구성

```
Nexus
├── REST API (FastAPI)
│   ├── Graph 쿼리 API   → AGE 'codebase' Cypher 쿼리
│   └── Rebuild 관리 API → 내부 Job Queue 제어
├── Internal Job Queue   → PostgreSQL jobs 테이블 기반
│   └── Worker           → graphify → loader → AGE 갱신
└── AGE Viewer (Docker)  → 시각화 + Cypher 쿼리 UI
```

---

## 4. REST API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | `/query` | 자연어 → 키워드 추출 → AGE BFS/DFS 탐색 |
| GET | `/node/{id}` | 특정 노드 상세 정보 |
| GET | `/neighbors/{id}` | 노드의 직접 연결 이웃 |
| GET | `/community/{id}` | 커뮤니티 멤버 노드 목록 |
| GET | `/god-nodes` | 최고 연결도 노드 목록 |
| GET | `/stats` | 그래프 기본 통계 |
| GET | `/path` | 두 노드 간 최단 경로 |
| POST | `/rebuild` | Rebuild job 큐에 등록 |
| GET | `/jobs/{id}` | Job 상태 조회 |
| GET | `/jobs` | 최근 Job 목록 |

---

## 5. Rebuild 파이프라인

```
트리거 (CI/CD webhook / cron / 수동)
    ↓
POST /rebuild
    ↓
Internal Job Queue (PostgreSQL jobs 테이블)
  → 순차 처리 (동시 실행 방지)
    ↓
graphify --update (변경 파일만 재처리)
    ↓
Loader (graph.json → AGE 'codebase')
    ↓
GET /jobs/{id} → completed
```

**Rebuild 전략:** daily 스케줄 (새벽) 또는 release 기준. PR마다 돌리지 않음.

**Rebuild 중 동작:** 새벽 스케줄 기준, 사용자 트래픽 없는 시간에 실행. `/query` 요청 시 503 반환.

---

## 6. 인프라

| 항목 | 값 |
|------|-----|
| 호스팅 | Hostinger |
| PostgreSQL | lightrag-pg:16-vector-age, 포트 5434 |
| AGE 버전 | 1.6.0 |
| pgvector 버전 | 0.8.1 |
| AGE 그래프 | `chunk_entity_relation` (LightRAG), `codebase` (Nexus) |
| DB | lightrag |

### 기존 서비스 포트

| 서비스 | 포트 |
|--------|------|
| Open WebUI | 3000 |
| LightRAG-pg | 5434 |
| Forge | 8003 |
| Nexus API | 8004 (예정) |
| AGE Viewer | 8005 (예정) |

---

## 7. 코드베이스 그래프 스키마 (AGE)

### 노드 레이블

| 레이블 | 설명 |
|--------|------|
| `CodeNode` | Java 클래스, 메서드, 파일 |
| `DocumentNode` | README, 문서 |
| `ImageNode` | 다이어그램, 이미지 |
| `HyperNode` | 논리적 그룹 (아키텍처 패턴 등) |

### 노드 프로퍼티

`id`, `label`, `file_type`, `source_file`, `source_location`, `community`, `norm_label`

### 엣지 타입 (10종)

`CALLS`, `METHOD`, `CONTAINS`, `IMPORTS`, `REFERENCES`, `EXTENDS`, `IMPLEMENTS`, `RATIONALE_FOR`, `CONCEPTUALLY_RELATED_TO`, `SEMANTICALLY_SIMILAR_TO`, `MEMBER_OF`

---

## 8. 스케일 예측

| 소스 크기 | 예상 노드 | 예상 엣지 | graph.json | Loader 소요 |
|----------|---------|---------|-----------|-----------|
| 12MB (POC) | 600 | 1,034 | 800KB | ~30초 |
| 100MB | ~5,000 | ~8,500 | ~7MB | ~4분 |
| 500MB | ~25,000 | ~42,000 | ~33MB | ~20분 |

---

## 9. 알려진 한계 및 후순위 작업

| 항목 | 현황 | 개선 시점 |
|------|------|---------|
| Loader MERGE | full wipe + CREATE | 고빈도 rebuild 필요 시 |
| 코드 노드 임베딩 | 없음 | 코드 유사도 검색 필요 시 |
| Cross-store 쿼리 | 오케스트레이터에서 처리 | 향후 |
| AGE 그래프 간 연결 | 없음 | 향후 |
