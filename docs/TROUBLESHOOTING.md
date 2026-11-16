# TROUBLESHOOTING

개발 중 겪은 문제를 기록한다. 원인을 모르거나 아직 해결 못 한 문제도 적는다. 같은 문제를 다시 만났을 때 빨리 찾아 쓰기 위한 문서다.

## 기록 규칙

- 문제를 만나면 원인·해결 여부와 관계없이 일단 기록한다.
- 항목은 상태에 따라 아래 세 구역 중 하나에 둔다. 상태가 바뀌면 항목을 **다음 구역으로 옮기고** 내용을 보완한다.
  1. **원인 미확인** — 증상만 알고 원인을 모른다.
  2. **원인 확인 · 미해결** — 원인은 알지만 아직 해결하지 못했다.
  3. **해결 완료** — 원인을 확인했고 해결까지 끝났다.
- 각 구역 안에서는 최신 항목을 맨 위에 둔다.
- 증상은 검색할 수 있게 **실제 에러 메시지 원문**을 그대로 적는다.
- 원인을 모를 때는 **확인된 사실**(재현 조건, 시도해 본 것과 결과)만 적고, 추측은 "추정"이라고 표시한다.
- 코드나 설정을 바꿨다면 파일 경로를 적는다. 긴 diff는 넣지 않는다.
- 비밀번호·토큰 등 비밀 값은 적지 않는다.
- 이미 있는 항목과 같은 문제면 새로 만들지 말고 기존 항목을 보완한다.

영역 태그: `backend`, `worker`, `frontend`, `infra`, `ci`, `기타`

### 항목 템플릿

```markdown
### [영역] 한 줄 제목

- **날짜**: YYYY-MM-DD (해결했다면 `→ YYYY-MM-DD 해결`)
- **증상**: 무엇이 어떻게 실패했는지. 에러 메시지 원문.
- **재현 조건**: 언제, 어떤 환경·명령에서 나는지. (알면)
- **시도한 것**: 해 본 조치와 결과. (원인 미확인·미해결일 때)
- **원인**: 근본 원인. (확인된 경우만. 구역 1에서는 생략하거나 "추정: …")
- **해결**: 실제로 한 조치 (명령어, 변경한 파일 경로). (구역 3만)
- **재발 방지**: 다음에 같은 일을 피하는 방법. 없으면 생략.
```

---

## 1. 원인 미확인

### [worker] 닫힌 포트로 psycopg 연결하면 25초가 넘도록 아무 로그 없이 멈춘 것처럼 보임

- **날짜**: 2026-11-16
- **증상**: 워커를 `CODEMAP_DATABASE_URL=postgresql://codemap:codemap@localhost:1/codemap`(닫힌 포트)로 띄우고 작업 메시지를 보냈더니, `waiting for jobs on 'analysis.jobs'` 뒤로 25초 동안 로그가 하나도 없었다. 종료 뒤 메시지 2개가 `analysis.jobs`에 그대로 남아 있었다(처리 중이던 메시지가 연결 종료로 되돌아온 것).
- **재현 조건**: Windows, 워커 `PgStore`가 `psycopg.connect`를 `connect_timeout` 없이 부를 때.
- **시도한 것**: URL에 `?connect_timeout=2`를 붙이니 재시도 2번 뒤 DLQ까지 40초 안에 정상 동작했다(`analysis.jobs.dlq`에 2건: 인프라 오류로 재시도를 다 쓴 작업 1건, 깨진 메시지 1건).
- **원인**: 확인 못 함. 추정: Windows에서 `localhost`가 IPv6(`::1`)와 IPv4를 차례로 시도하고, 거부된 연결 재시도에 시간이 오래 걸린다.
- **재발 방지(임시)**: 운영 DB URL에는 `connect_timeout`을 넣는다. `PgStore`에 기본값을 넣을지는 Phase 2에서 정한다.

### [기타] Bash 도구 heredoc으로 Java 파일을 만들면 `\\d`가 `\d`로 저장되고, 긴 스크립트는 파싱 오류로 통째로 취소됨

- **날짜**: 2026-11-16
- **증상**:
  - A. 여러 파일을 `cat > … <<'EOF'`로 한 번에 만드는 긴 스크립트가 `/usr/bin/bash: -c: line 289: unexpected EOF while looking for matching `''`로 실패했고, 스크립트 안의 명령이 하나도 실행되지 않았다(만들려던 디렉터리의 파일이 전부 없었다).
  - B. 작은따옴표로 감싼 heredoc(`<<'EOF'`)에 `Pattern.compile("j_(\\d{1,18})")`를 적었는데, 저장된 `backend/src/main/java/com/codemap/api/common/PublicId.java`에는 `"j_(\d{1,18})"`(백슬래시 1개)가 들어 있었다. 컴파일 오류: `error: illegal escape character`.
- **재현 조건**: Windows Git Bash(Claude Code Bash 도구)에서 Java 코드가 든 긴 heredoc 스크립트를 한 번에 실행할 때.
- **시도한 것**: 파일을 Write 도구로 하나씩 만들고, 정규식은 `\d` 대신 `[0-9]`로 바꿨다. 이후 같은 증상은 없었다.
- **원인**: 확인 못 함. 추정: Bash 도구로 명령이 넘어가는 과정 어딘가에서 백슬래시 이스케이프가 한 번 풀린다. A의 파싱 오류 위치(`line 289`의 `'`)도 추적하지 않았다.
- **재발 방지(임시)**: 소스 파일은 heredoc 대신 Write 도구로 만든다. 백슬래시가 든 문자열은 만든 뒤 컴파일로 확인한다.

## 2. 원인 확인 · 미해결

아직 기록된 문제가 없다.

## 3. 해결 완료

### [backend] Hibernate 스키마 검증 실패: `missing column [semx] in table [code_node]`

- **날짜**: 2026-11-16 → 2026-11-16 해결
- **증상**: `./gradlew test`에서 앱 컨텍스트가 뜨지 않았다(`ddl-auto=validate`). `SchemaManagementException: Schema validation: missing column [semx] in table [code_node]`
- **재현 조건**: 엔티티 필드 `semX`, `semY`, `semZ`를 컬럼 이름 지정 없이 `V2__pipeline.sql`의 `sem_x`, `sem_y`, `sem_z`에 매핑했을 때.
- **원인**: 필드 `semX`가 `sem_x`가 아니라 `semx` 컬럼으로 매핑됐다. 카멜 케이스를 스네이크 케이스로 바꾸는 기본 규칙이 대문자 한 글자로 끝나는 이름에서 `_`를 넣지 않는 것으로 보인다(추정, 규칙 자체는 확인하지 않음).
- **해결**: `backend/src/main/java/com/codemap/api/graph/CodeNode.java`의 세 필드에 `@Column(name = "sem_x")` 등을 명시했다.
- **재발 방지**: 대문자 한 글자로 끝나는 필드(`semX`, `posY` 등)는 컬럼 이름을 명시한다. `validate` 설정 덕분에 기동 시점에 바로 드러난다.

### [infra] `docker compose up -d` 실패: Docker API에 연결할 수 없음

- **날짜**: 2026-11-16 → 2026-11-16 해결
- **증상**: `unable to get image 'redis:7-alpine': failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.`
- **재현 조건**: Windows에서 Docker Desktop이 꺼진 채 저장소 루트에서 `docker compose up -d`를 실행할 때.
- **원인**: Docker Desktop(데몬)이 실행 중이 아니었다.
- **해결**: Docker Desktop을 켠 뒤 `docker compose up -d`를 다시 실행했다. PostgreSQL은 `docker compose ps`의 healthy로, Redis는 `redis-cli ping`으로, RabbitMQ는 관리 API(`localhost:15682`)가 200을 주는지로 확인했다. Redis와 RabbitMQ는 healthcheck가 없어 `ps`만으로는 준비 여부를 알 수 없다.
- **재발 방지**: 인프라 명령 전에 Docker Desktop이 켜져 있는지 확인한다.
