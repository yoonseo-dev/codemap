# Phase 1 체크리스트 — 파이프라인 골격

2026-11-16 작성 · 개인 진행 기록(커밋하지 않음)

**완료 기준:** 브라우저에서 저장소 주소를 입력하면 다음이 실제로 이어진다.
`프론트 → POST /api/analyses → DB 저장 → RabbitMQ → 워커 → 5단계 진행률(Redis Stream → SSE) → 가짜 그래프 DB 저장 → GET /graph → 3D 지도`

- 주소와 응답 모양은 [API_CONTRACT.md](API_CONTRACT.md)와 `frontend/src/api/types.ts`를 따른다.
- 분석 로직은 전부 **가짜**다. 이번 목표는 "부품끼리 실제로 말이 통하는가"이다.
- 각 항목은 **무엇을 / 왜 / 어디에 / 다 됐는지 어떻게 확인하나** 순서로 적었다.

---

## 0. 준비

- [ ] **0-1 PR #1 머지**
  - 무엇: `feat/frontend-screens` → `dev`를 merge commit으로 머지 (`gh pr merge 1 --merge`)
  - 왜: 프론트 화면이 dev에 있어야 이번 브랜치에서 실제 백엔드와 붙여 볼 수 있다.
  - 확인: `git log dev`에 커밋 3개(API 계약, 프론트 화면, CI)가 보인다.
- [ ] **0-2 작업 브랜치 만들기**
  - 무엇: `git checkout dev && git pull` → `git checkout -b feat/pipeline-skeleton`
- [ ] **0-3 체크리스트 무시 규칙 커밋**
  - 무엇: 이 파일을 `.gitignore`에 넣은 변경을 새 브랜치의 첫 커밋으로 넣는다.
  - 왜: 지금 브랜치에서 커밋하면 PR #1에 섞인다.
- [ ] **0-4 로컬 인프라 확인**
  - 무엇: `docker compose up -d` → PostgreSQL(5442), Redis(6389), RabbitMQ(5682, 콘솔 15682)가 모두 떠 있는지 확인
  - 확인: `docker compose ps`가 healthy, `http://localhost:15682` 로그인 가능

## 결정할 것 (작업 전에)

- [ ] **D-1 인증을 이번에 할지**
  - 제안: 이번에는 빼고 Security를 전부 열어 둔다. 로그인 주소가 계약에서 아직 미정이고, 파이프라인 관통과는 관계가 없다.
- [ ] **D-2 진행률 전달 방식**
  - 제안: Redis **Stream**. pub/sub은 연결이 끊긴 동안의 이벤트를 잃어서 계약의 `Last-Event-ID` 재접속을 맞추려면 "마지막 진행률 키"를 따로 둬야 한다. Stream은 이벤트마다 ID가 있어 놓친 것부터 다시 읽을 수 있다.
  - 정하면: `DEVELOPMENT_PLAN.md` Phase 1의 pub/sub 설명을 고친다(7-6).

## 설계 결정 요약

| 항목 | 결정 |
| --- | --- |
| 진행률 전달 | Redis Stream `job:{id}:events`, 이벤트 ID를 SSE `id`로 그대로 씀 |
| 단계 상태 | `job_stage` 테이블 (작업당 5행) |
| DB 쓰기 주체 | 작업·단계 생성은 백엔드, 진행 중 갱신과 결과 저장은 워커(psycopg) |
| 가짜 그래프 | 워커가 `code_node`/`code_edge`에 저장 → 백엔드가 읽어서 계약 모양으로 |
| ID | DB는 bigint, API는 `j_12`, `r_3` 같은 문자열 |
| 캐시 | 같은 저장소 + 같은 HEAD 커밋에 끝난 작업이 있으면 그걸 반환 (`cached: true`) |
| 실패 | 분석 중 오류는 DB에 `FAILED`로 기록하고 끝. 인프라 오류(DB·Redis 끊김 등)만 RabbitMQ 재시도 2회 → DLQ |

---

## 1. DB 스키마 — `V2__pipeline.sql`

파일: `backend/src/main/resources/db/migration/V2__pipeline.sql`
Flyway는 백엔드가 띄울 때 실행한다. 워커는 스키마를 만들지 않는다.

- [ ] **1-1 `repository`에 컬럼 추가**
  - `owner TEXT`, `name TEXT`, `default_branch TEXT`
  - 왜: 응답의 `repository: { owner, name, url }`과 커밋 정보의 `branch`에 필요하다.
- [ ] **1-2 `analysis_job`에 컬럼 추가**
  - `branch TEXT`, `commit_date TIMESTAMPTZ`, `started_at TIMESTAMPTZ`
  - 실패 정보: `failure_stage TEXT`, `failure_code TEXT`, `failure_message TEXT`, `failure_resumable BOOLEAN`
  - `status`에 CHECK 제약 (`QUEUED/RUNNING/DONE/FAILED`)
  - 인덱스 `(repository_id, commit_sha)`: 캐시 조회용
- [ ] **1-3 `job_stage` 테이블 만들기**
  - 컬럼: `job_id` FK, `stage`, `position SMALLINT`(순서 0~4), `status`(`PENDING/RUNNING/DONE/FAILED/CANCELLED`), `percent SMALLINT`, `detail TEXT`, `metrics JSONB DEFAULT '{}'`, `updated_at`
  - PK: `(job_id, stage)`
  - 왜: `GET /api/jobs/{id}`가 단계 5개의 상태를 배열로 돌려줘야 한다. 지금 `analysis_job.stage`는 "현재 단계" 하나만 담는다.
- [ ] **1-4 `code_node` 테이블 만들기**
  - 컬럼: `job_id` FK, `node_id TEXT`(`파일경로::클래스.함수`), `name`, `path`, `module_id`, `kind`, `start_line`, `end_line`, `degree`, `sem_x/sem_y/sem_z REAL`
  - PK: `(job_id, node_id)`
  - 계약의 `GraphNode` 필드와 1:1로 맞춘다.
- [ ] **1-5 `code_edge` 테이블 만들기**
  - 컬럼: `id BIGSERIAL`, `job_id` FK, `source`, `target`, `kind`(`call/import/similar/cochange`), `weight DOUBLE PRECISION`, `since TIMESTAMPTZ NULL`
  - 인덱스: `(job_id, kind)`. Phase 6에서 종류별로 나눠 받을 때 쓴다.
  - 모듈 목록(`modules`)은 테이블을 따로 두지 않고 `code_node.module_id`로 묶어서 계산한다(6-1).
- [ ] **1-6 확인**
  - `./gradlew bootRun`이 오류 없이 뜬다.
  - psql `\d job_stage` 등으로 테이블이 생긴 걸 본다.
  - `flyway_schema_history`에 V2가 있다.

## 2. 백엔드 공통 기반

패키지 제안: `com.codemap.api.common`(오류·ID·설정), `.analysis`(저장소·작업 생성), `.job`(조회·SSE·재시도), `.graph`(지도)

- [ ] **2-1 오류 코드 목록 `ErrorCode` enum**
  - 각 코드에 HTTP 상태, 화면용 한국어 `message`, `hint`를 둔다. 문구는 계약 표를 그대로 쓴다.
  - 코드: `INVALID_URL`(400), `REPO_NOT_FOUND`(404), `UNSUPPORTED_LANGUAGE`(422), `REPO_TOO_LARGE`(413), `JOB_NOT_FOUND`(404), `JOB_NOT_READY`(409), `NOT_RESUMABLE`(409), `INVALID_REQUEST`(400), `INTERNAL`(500)
- [ ] **2-2 `ApiException` + 전역 처리기 `GlobalExceptionHandler`**
  - `@RestControllerAdvice`에서 모든 오류를 `{ "error": { code, message, hint } }`로 바꾼다.
  - 요청 본문 검증 실패는 `INVALID_REQUEST`로 처리한다.
  - 예상 못 한 예외는 `INTERNAL`로 처리한다. 메시지는 일반 문구로 하고, 스택은 로그에만 남긴다.
  - 확인: 없는 작업 조회 시 404와 계약 모양의 본문이 나온다.
- [ ] **2-3 `SecurityConfig` (D-1이 "이번엔 뺌"일 때)**
  - 모든 요청 허용, CSRF 끄기, 세션 없음(STATELESS)
  - 왜: starter-security가 이미 들어 있어서, 아무 설정이 없으면 모든 요청이 401이 된다.
  - CORS 설정은 필요 없다. Vite가 `/api`를 프록시한다.
- [ ] **2-4 ID 변환기 `PublicId`**
  - `j_12` ↔ `12`, `r_3` ↔ `3` 변환
  - 형식이 틀린 ID는 `JOB_NOT_FOUND`로 처리한다. 400이 아닌 이유: 화면 입장에선 "없는 작업"과 같다.
  - 단위 테스트를 붙인다.
- [ ] **2-5 JPA 엔티티와 Spring Data 리포지토리**
  - `SourceRepo`(테이블 `repository`): `Repository`라는 이름이 Spring Data 인터페이스와 겹쳐서 피한다.
  - `AnalysisJob`, `JobStage`(복합키), `CodeNode`(복합키), `CodeEdge`
  - `metrics` JSONB는 `@JdbcTypeCode(SqlTypes.JSON)` + `Map<String, Object>`로 매핑한다.
  - 확인: `ddl-auto=validate` 상태로 앱이 뜬다. 엔티티와 V2 스키마가 맞는다는 뜻이다.
- [ ] **2-6 공통 설정**
  - `spring.threads.virtual.enabled=true`: SSE 연결마다 스레드를 하나씩 쓰므로 가상 스레드로 비용을 줄인다(5-2).
  - 날짜는 ISO 8601 문자열로 직렬화하고, `null` 필드도 응답에 포함한다. 계약 예시에 `"finishedAt": null`이 있다.

## 3. 분석 시작 — `POST /api/analyses`

- [ ] **3-1 저장소 주소 해석기 `RepoUrlParser`**
  - 받는 형식: `owner/repo`, `github.com/owner/repo`, `https://github.com/owner/repo`, 끝의 `.git`이나 `/`가 붙은 것
  - 결과: `owner`, `name`, 정규화된 `https://github.com/owner/repo`
  - 그 외(다른 호스트, 경로 부족 등)는 `INVALID_URL`로 처리한다.
  - 확인: 입력과 기대값 표로 된 파라미터 테스트가 통과한다.
- [ ] **3-2 원격 저장소 확인기 `RemoteGit`**
  - `git ls-remote --symref <url> HEAD`를 실행해 HEAD 커밋 SHA와 기본 브랜치를 얻는다.
  - 환경변수 `GIT_TERMINAL_PROMPT=0`: 비공개 저장소에서 비밀번호 입력을 기다리며 멈추지 않고 바로 실패하게 한다.
  - 타임아웃 10초를 두고, 실패하거나 시간이 지나면 `REPO_NOT_FOUND`로 처리한다.
  - 인터페이스로 만들어 테스트에서는 가짜 구현을 쓴다. 테스트가 인터넷에 의존하지 않게 하기 위해서다.
- [ ] **3-3 RabbitMQ 설정 `AmqpConfig`**
  - 큐 `analysis.jobs`: durable, 실패 시 `analysis.jobs.retry`로 넘기는 dead-letter 인자 설정
  - 큐 `analysis.jobs.retry`: TTL 5초가 지나면 다시 `analysis.jobs`로 돌아온다. 재시도 대기실 역할이다.
  - 큐 `analysis.jobs.dlq`: 2번 재시도해도 실패한 메시지를 보관한다.
  - 메시지는 JSON 변환기(`JacksonJsonMessageConverter`)로 보낸다.
  - ⚠️ 워커도 같은 큐를 선언하므로 인자가 한 글자라도 다르면 `PRECONDITION_FAILED`로 연결이 끊긴다. 양쪽 값을 똑같이 맞춘다(4-9).
- [ ] **3-4 작업 메시지 모양 정하기**
  - `{ "jobId": 12, "repoUrl": "https://github.com/o/r", "commitSha": "a3f9…", "fromStage": null }`
  - `fromStage`는 재시도할 때 시작 단계다(6-2). 처음 실행이면 null이다.
  - 워커의 `JobMessage`(4-2)와 같은 필드여야 한다.
- [ ] **3-5 `AnalysisService.start(repo)`**
  1. 주소를 해석하고(3-1) HEAD를 확인한다(3-2). 이 과정은 트랜잭션 밖에서 한다(네트워크 호출이라서).
  2. 저장소를 찾거나 새로 만든다(URL UNIQUE).
  3. 같은 저장소와 같은 SHA로 `DONE`인 작업이 있으면 그 작업을 `cached: true`로 반환하고 끝낸다.
  4. 같은 SHA로 `QUEUED/RUNNING`인 작업이 있으면 그 작업을 반환한다(`cached: false`). 두 번 눌러도 작업이 둘 생기지 않게 하기 위해서다.
  5. 아니면 작업(`QUEUED`)과 단계 5행(`PENDING`, 0%)을 만든다.
  6. **트랜잭션 커밋 뒤에** 큐에 발행한다(`@TransactionalEventListener(AFTER_COMMIT)`). 커밋 전에 발행하면 워커가 아직 없는 작업 행을 읽을 수 있다.
- [ ] **3-6 `AnalysisController`**
  - 요청 `{ "repo": "..." }`(빈 값이면 `INVALID_REQUEST`), 응답 201 `{ jobId, repository, status, cached }`
- [ ] **3-7 `GET /api/repositories/recent`**
  - 01 화면의 "최근 분석" 목록이다. 계약의 응답 모양을 확인한 뒤 끝난 작업이 있는 저장소를 최신순으로 N개 돌려준다.
  - 이번 범위에서 빼도 된다. 빼면 프론트 mock을 유지한다(7-1).
- [ ] **3-8 테스트**
  - 주소 해석기 단위 테스트
  - 서비스 테스트(가짜 RemoteGit, RabbitTemplate 목): 새 작업이면 발행 1회, 캐시면 발행 0회, 진행 중인 작업이 있으면 그 작업 반환
  - MockMvc: 201 정상, 400 `INVALID_URL`, 404 `REPO_NOT_FOUND`의 본문 모양
- 참고: `UNSUPPORTED_LANGUAGE`, `REPO_TOO_LARGE`는 clone해 봐야 알 수 있다. Phase 2에서 워커의 INGEST 단계 실패로 처리한다.

## 4. 워커 파이프라인 골격

파일 제안(`worker/src/codemap_worker/`): `messages.py`, `pipeline.py`, `stages.py`, `events.py`, `store.py`, `fake_graph.py`, `main.py`
원칙: 실행기(`pipeline.py`)는 DB와 Redis를 직접 모르고 `store`·`events` 인터페이스만 받는다. 그래야 인프라 없이 테스트할 수 있다.

- [ ] **4-1 설정 추가 (`config.py`)**
  - `fake_stage_seconds: float = 1.0`: 가짜 단계 하나에 걸리는 시간. 테스트에서는 0으로 둔다.
  - `fake_fail_stage: str | None = None`: 지정한 단계에서 일부러 실패시킨다. 실패와 재시도 화면을 확인하는 용도다.
  - `event_stream_ttl_hours: int = 24`
- [ ] **4-2 작업 메시지 `JobMessage` (pydantic)**
  - 3-4와 같은 필드다. 파싱에 실패하면 재시도해도 소용없으므로 바로 DLQ로 보내고 로그를 남긴다.
- [ ] **4-3 단계 정의 (`stages.py`)**
  - 순서: `INGEST → STRUCTURE → SEMANTIC → HISTORY → DIVERGENCE`
  - 단계 함수 모양: `run(ctx, report)`. 여기서 `report(percent, detail, metrics)`는 진행률을 알리는 콜백이다.
  - 가짜 구현: 0→100%를 5번에 나눠 올리며 `fake_stage_seconds`만큼 쉰다. detail과 metrics는 계약 예시처럼 그럴듯한 값을 넣는다(예: "함수 2,418개 중 1,546개 임베딩").
  - Phase 2부터는 이 함수 안만 진짜 로직으로 바꾼다.
- [ ] **4-4 이벤트 발행기 (`events.py`)**
  - `XADD job:{id}:events MAXLEN ~ 1000 * type <type> data <JSON>`
  - `data`는 프론트 `JobEvent`와 정확히 같은 모양이다: `{"type":"stage","stage":{…}}`, `{"type":"done","jobId":"j_12"}`, `{"type":"failed","failure":{…}}`
  - 첫 기록 때 키에 만료 시간(24시간)을 건다. 오래된 스트림이 Redis에 쌓이지 않게 하기 위해서다.
  - ⚠️ jobId는 API와 같은 `j_` 형식으로 넣는다. 형식을 만드는 규칙은 백엔드 2-4와 같아야 한다.
- [ ] **4-5 DB 저장소 (`store.py`, psycopg)**
  - `mark_job_running(job_id)`: status RUNNING, `started_at` 기록
  - `update_stage(job_id, stage, status, percent, detail, metrics)`: `analysis_job.stage`도 함께 갱신
  - `mark_job_done(job_id)`, `mark_job_failed(job_id, failure)`: 뒤 단계를 `CANCELLED`로 바꾸는 것까지 한 트랜잭션에서 한다.
  - `save_graph(job_id, nodes, edges)`: 같은 작업의 기존 행을 지우고 다시 넣는다.
  - **모든 함수는 두 번 실행돼도 결과가 같아야 한다.** RabbitMQ 재전달로 같은 작업이 다시 올 수 있기 때문이다.
- [ ] **4-6 진행률 쓰기 줄이기**
  - DB 쓰기와 이벤트 발행은 같은 단계에서 0.5초에 한 번 이하로 한다. 단 시작, 완료, 실패는 항상 바로 쓴다.
  - 왜: Phase 4 임베딩처럼 함수마다 진행률을 올리면 수천 번 쓰게 된다. 구조를 지금 잡아 둔다.
- [ ] **4-7 가짜 그래프 생성기 (`fake_graph.py`)**
  - 시드를 고정해 실행할 때마다 같은 결과가 나오게 한다. 모듈 6개 안팎, 함수 약 200개.
  - 엣지는 4종류를 모두 만든다: `call`, `import`, `similar`(weight 0~1), `cochange`(`since` 포함)
  - 노드 ID는 `billing/invoice.py::InvoiceService.create` 형식이고, `semanticPosition`과 `degree`를 채운다.
  - 프론트 mock(`frontend/src/api/mock/fixtures.ts`)과 비슷한 모양으로 만들어 화면을 비교하기 쉽게 한다.
- [ ] **4-8 실행기 (`pipeline.py`)**
  1. 작업을 RUNNING으로 바꾼다.
  2. `fromStage`부터 각 단계를 RUNNING으로 두고 실행한 뒤 DONE(100%)으로 바꾼다. 앞 단계는 건너뛴다.
  3. 다 끝나면 가짜 그래프를 저장하고, 작업을 DONE으로 바꾸고, `done` 이벤트를 발행한다.
  - 단계가 실패하면:
    - 단계 함수는 실패를 `StageError(code, message, resumable)`로 알린다. 그 밖의 예외는 `INTERNAL`이며 resumable=true로 본다.
    - 해당 단계는 FAILED, 뒤 단계는 CANCELLED, 작업은 FAILED로 바꾸고 `failure`를 기록한 뒤 `failed` 이벤트를 발행한다.
    - 메시지는 **ack**한다. 분석 실패는 이미 기록했으니 재시도할 대상이 아니다.
- [ ] **4-9 소비자 (`main.py`)**
  - 큐 3개를 3-3과 **똑같은 인자로** 선언한다.
  - 분석 실패(4-8)가 아닌 오류, 즉 DB나 Redis 연결 끊김 같은 경우:
    - `x-death` 헤더의 재시도 횟수가 2 미만이면 nack(requeue=False)한다. 메시지는 retry 큐로 갔다가 5초 뒤 돌아온다.
    - 2 이상이면 DLQ로 보내고 ack한다.
  - RabbitMQ 연결이 끊기면 몇 초 뒤 다시 연결하고, Ctrl+C로 깔끔하게 종료되게 한다.
  - `prefetch_count=1`은 유지한다. 한 번에 작업 하나씩 처리한다.
- [ ] **4-10 테스트 (pytest, 인프라 없이)**
  - 메모리 안의 가짜 store·events로 실행기를 돌린다.
  - 성공: 이벤트가 stage 순서대로 나오고 마지막이 `done`이다. 그래프가 저장된다.
  - 실패(`fake_fail_stage=SEMANTIC`): SEMANTIC은 FAILED, HISTORY와 DIVERGENCE는 CANCELLED, `failed` 이벤트가 나온다.
  - 재시도(`fromStage=SEMANTIC`): INGEST와 STRUCTURE를 다시 실행하지 않는다.
  - 가짜 그래프: 노드 ID가 겹치지 않고, 모든 엣지의 양 끝이 실제 노드다.
  - 메시지 파싱 실패 처리
  - `ruff check .` 통과

## 5. 작업 조회와 실시간 진행률

- [ ] **5-1 `GET /api/jobs/{jobId}`**
  - 응답: `repository`, `commit { sha, branch, date }`, `status`, `stage`, `stages[]`(position 순), `startedAt`, `finishedAt`, `failure`(없으면 null)
  - `commit.date`는 ls-remote로 알 수 없다. 이번에는 null이고, Phase 2 INGEST에서 워커가 채운다. 프론트가 null을 견디는지 확인한다.
  - 없는 작업이면 `JOB_NOT_FOUND`
- [ ] **5-2 `GET /api/jobs/{jobId}/events` (SSE)**
  - `SseEmitter`(타임아웃 30분)를 만들고, 가상 스레드 하나가 Redis Stream을 읽어 보낸다.
  - 읽는 방식은 `XRANGE`를 0.5초마다 폴링한다.
    - 왜 `XREAD BLOCK`이 아닌가: Lettuce 공유 연결에서 BLOCK을 쓰면 다른 Redis 요청까지 막힌다. 연결마다 전용 연결을 두는 것보다 폴링이 단순하다.
  - 시작 위치: `Last-Event-ID` 헤더가 있으면 그 다음부터, 없으면 처음부터 보낸다. 스트림이 짧아서 처음부터 보내도 문제없다.
  - Redis Stream ID(`1731…-0`)를 SSE `id`로, `type`을 SSE `event` 이름으로 쓴다.
  - 15초마다 주석 줄(`: ping`)을 보내 프록시가 연결을 끊지 않게 한다.
  - `done`이나 `failed`를 보낸 뒤 emitter를 닫는다.
  - 스트림이 이미 만료됐는데 작업이 끝나 있으면, DB 상태로 `done`/`failed` 하나를 만들어 보내고 닫는다.
  - 클라이언트가 떠나면(onCompletion/onTimeout/onError) 폴링을 멈춘다. 스레드가 새지 않게 하기 위해서다.
- [ ] **5-3 Vite 프록시에서 SSE 확인**
  - 이벤트가 모였다가 한꺼번에 오지 않는지(버퍼링) 확인한다. 문제가 있으면 응답 헤더에 `X-Accel-Buffering: no`, `Cache-Control: no-cache`를 넣는다.
- [ ] **5-4 테스트**
  - Redis Stream에 이벤트를 미리 넣어 두고 SSE 응답에 순서대로 오는지 본다.
  - `Last-Event-ID`를 주면 그 뒤 이벤트만 오는지 본다.
  - 스트림이 없는 끝난 작업이면 이벤트 하나만 오고 닫히는지 본다.

## 6. 지도 데이터와 재시도

- [ ] **6-1 `GET /api/jobs/{jobId}/graph`**
  - 작업이 DONE이 아니면 409 `JOB_NOT_READY`
  - `nodes`, `edges`: 테이블을 계약 모양으로 바꾼다. `lines: [start, end]`, `semanticPosition: [x, y, z]`, `since`는 cochange에만 넣는다.
  - `modules`: `module_id`로 묶고, 각 묶음에서 degree가 가장 큰 노드를 `hubNodeId`로 한다.
  - `stats`: `functions`는 노드 수, `files`는 path 종류 수, `commits`는 INGEST 단계 metrics의 `commits`
  - 확인: 프론트 지도 화면이 이 응답으로 뜬다.
- [ ] **6-2 `POST /api/jobs/{jobId}/retry`**
  - 조건: status가 FAILED이고 `failure_resumable`이 true. 아니면 409 `NOT_RESUMABLE`
  - 할 일:
    - 실패한 단계와 그 뒤 단계를 PENDING(0%)으로 돌린다.
    - 작업을 QUEUED로 바꾸고 failure를 비운다.
    - 커밋 뒤에 `fromStage=실패단계`로 발행한다.
    - 응답은 `Job`(5-1과 같은 모양)이다.
  - 버튼을 두 번 눌러도 한 번만 발행되게, `UPDATE … WHERE status='FAILED'`의 영향받은 행 수로 확인한다.
- [ ] **6-3 테스트**
  - graph: 진행 중이면 409, 끝났으면 계약 모양
  - retry: 성공 시 단계가 초기화되고 발행 1회. 두 번째 요청은 409

## 7. 연결과 마무리

- [ ] **7-1 프론트 API 섞어 쓰기 모드**
  - 문제: 지금 `frontend/src/api/index.ts`는 `VITE_API=http`이면 **전부** 실제 백엔드로 보낸다. 백엔드에 없는 divergences, search, shares, timeline, nodes 요청이 모두 실패한다.
  - 할 일: `VITE_API=hybrid`를 추가한다. 이번에 만든 엔드포인트(analyses, jobs, events, retry, graph)만 http로 보내고, 나머지는 mock으로 보낸다.
  - 확인: hybrid 모드에서 지도 화면의 어긋남 패널이 mock 데이터로 뜬다.
- [ ] **7-2 끝까지 한 번 돌려 보기**
  - 띄우는 순서: `docker compose up -d` → 백엔드 `bootRun` → 워커 → 프론트(`VITE_API=hybrid npm run dev`)
  - 저장소 입력 → 02 화면에서 5단계가 차례로 올라감 → 03 지도에 가짜 그래프가 뜸
- [ ] **7-3 실패와 재시도 흐름**
  - `CODEMAP_FAKE_FAIL_STAGE=SEMANTIC`으로 워커를 띄운다 → 02-오류 화면이 뜬다 → 설정을 빼고 워커를 재시작한다 → "다시 시도" → SEMANTIC부터 이어서 끝난다.
- [ ] **7-4 재접속과 캐시**
  - 분석 중에 새로고침하면 진행률이 끊기지 않고 이어진다.
  - 같은 저장소를 다시 입력하면 바로 지도로 간다(`cached: true`).
  - 워커를 끈 채로 분석을 시작하면 QUEUED로 기다리다가, 워커를 켜면 진행된다.
- [ ] **7-5 CI 확인**
  - backend 테스트가 CI의 Postgres·Redis·RabbitMQ 서비스 컨테이너에서 통과한다.
  - 워커 테스트는 인프라 없이 통과한다.
- [ ] **7-6 문서 갱신**
  - `DEVELOPMENT_PLAN.md`: Phase 1의 pub/sub을 Stream으로 바꾸고 "실행 방법"을 갱신한다.
  - `API_CONTRACT.md`: 구현하면서 바뀐 점이 있으면 반영한다(예: `commit.date`가 null일 수 있음).
- [ ] **7-7 PR**
  - `feat/pipeline-skeleton` → `dev`. 설명에 완료 기준 확인 결과(7-2~7-4)를 적는다.
