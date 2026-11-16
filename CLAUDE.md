# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

GitHub 저장소를 입력받아 코드 관계를 **구조(호출·import) / 의미(코드 임베딩) / 역사(함께 수정된 이력)** 세 지도로 만들고, 세 지도가 어긋나는 지점(중복 구현, 숨은 결합, 책임 혼재)을 3D로 보여주는 서비스. 상세 기획은 `docs/PROJECT_PLAN.md`, Phase별 일정·완료 기준은 `DEVELOPMENT_PLAN.md`. 문서는 한국어로 작성되어 있다.

현재는 Phase 1(가짜 데이터로 end-to-end 파이프라인 골격) 단계이며, 대부분의 모듈은 빈 스켈레톤이다. 새 작업 전에 `DEVELOPMENT_PLAN.md`에서 해당 Phase의 범위를 확인할 것.

## Architecture

모노레포, 세 애플리케이션이 인프라(Postgres/Redis/RabbitMQ)로 연결된다.

- `backend/` — Spring Boot 4.1 (Java 21, Gradle) API 서버, 포트 8081. 저장소 등록·분석 작업 관리·결과 조회. 스키마는 **Flyway**(`src/main/resources/db/migration`)가 관리하고 `ddl-auto=validate`이므로, 엔티티를 바꾸면 반드시 마이그레이션을 추가해야 한다. 패키지 루트는 `com.codemap.api`.
- `worker/` — Python 3.11 분석 워커(`codemap_worker`). RabbitMQ `analysis.jobs` 큐(durable, prefetch=1)에서 작업을 받아 `handle_job`에서 파이프라인 실행. 단계별 서브패키지: `ingest → structure → semantic → history → divergence`, 그리고 `validation`.
- `frontend/` — React 19 + TypeScript + Vite, 3D는 react-three-fiber, 상태는 zustand, 서버 상태는 react-query, 코드 뷰어는 Monaco.
- 흐름: API가 작업을 RabbitMQ에 발행 → 워커가 처리하며 Redis로 진행률 발행 → API가 SSE로 브라우저에 전달. (`DEVELOPMENT_PLAN.md`는 Pub/Sub으로 적혀 있으나 Stream으로 바꿀지 검토 중이다.) 결과(노드·엣지·임베딩 벡터)는 PostgreSQL + pgvector에 저장.
- 설계 원칙: 워커의 각 분석 단계는 "입력 → 순수 함수 → 결과 객체"로 만들고 DB 저장은 분리해, DB 없이 샘플 저장소 픽스처로 단위 테스트한다.

## Local infra

호스트 포트가 기본값에서 +10 이동되어 있다 (다른 로컬 프로젝트와 충돌 방지): Postgres `5442`, Redis `6389`, RabbitMQ `5682` (관리 콘솔 `http://localhost:15682`). 계정은 모두 `codemap/codemap`.

```bash
docker compose up -d        # 루트에서 인프라 실행
```

## Commands

CI(`.github/workflows/ci.yml`)가 아래 명령을 그대로 실행한다. 백엔드 테스트·빌드는 인프라가 떠 있어야 한다.

```bash
# backend (backend/)
./gradlew build
./gradlew test --tests com.codemap.api.ApiApplicationTests   # 단일 테스트
./gradlew bootRun

# worker (worker/)
pip install -e ".[dev]"      # 임베딩 모델은 Phase 4에서: pip install -e ".[embed]" (torch 포함, 큼)
ruff check .
pytest -q
pytest tests/test_smoke.py::test_name -q                      # 단일 테스트
python -m codemap_worker.main                                 # 워커 실행

# frontend (frontend/)
npm ci
npm run dev
npm run lint                 # oxlint
npm run build                # tsc -b && vite build
```

## Conventions

- Python: ruff, line-length 100.
- 워커 설정은 `codemap_worker/config.py`(pydantic-settings)에서 읽는다.

## Troubleshooting log

에러·빌드 실패·환경 문제를 만나면 원인·해결 여부와 상관없이 작업을 끝내기 전에 `docs/TROUBLESHOOTING.md`에 기록한다. 형식과 규칙은 그 파일 상단을 따른다.

- 기록 대상: 원인을 찾는 데 시간이 걸렸거나 다시 겪을 만한 문제. 오타·단순 실수처럼 자명한 건 제외.
- 상태별 구역에 나눠 적는다: ① 원인 미확인 ② 원인 확인·미해결 ③ 해결 완료. 상태가 바뀌면 항목을 다음 구역으로 옮기고 내용을 보완한다.
- 원인을 모르면 추측으로 채우지 말고 확인된 사실(에러 원문, 재현 조건, 시도한 것과 결과)만 적는다. 추측은 "추정"으로 표시한다.
- 해결했다면 에러 메시지 원문, 원인, 해결 조치(변경한 파일 경로), 필요하면 재발 방지를 적는다.
- 새 문제를 만나면 먼저 이 파일에 같은 증상이 있는지 확인한다.
