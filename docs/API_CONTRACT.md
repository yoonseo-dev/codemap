# API 계약

2026-11-04 · 프론트와 백엔드가 주고받는 데이터 모양. 타입 정의는 [frontend/src/api/types.ts](../frontend/src/api/types.ts)가 기준이고, 이 문서는 주소와 예시를 설명합니다.

프론트는 이 모양 그대로 만든 가짜 데이터로 먼저 개발하고, 백엔드가 같은 모양으로 응답하면 주소만 바꿔 연결합니다.

## 공통 규칙

- **주소:** 모두 `/api`로 시작합니다. 개발 중에는 Vite가 `/api`를 `http://localhost:8081`(Spring Boot)로 넘깁니다.
- **인증:** 로그인이 필요한 요청은 `Authorization: Bearer <JWT>`를 붙입니다. 공유 링크 조회(`GET /api/shares/{token}`)만 로그인 없이 됩니다.
- **ID:** 모두 문자열입니다. 함수 ID(`NodeId`)는 `파일경로::클래스.함수` 형태입니다.
- **날짜:** ISO 8601 문자열입니다(`2026-10-28T14:02:00Z`).
- **오류:** 4xx·5xx 응답 본문은 항상 같은 모양입니다. `message`는 화면에 그대로 보여줄 수 있는 한국어 문장입니다.

```json
{ "error": { "code": "REPO_NOT_FOUND", "message": "이 저장소를 열 수 없어요", "hint": "공개 저장소의 주소인지 확인해 주세요. 예: github.com/owner/repo" } }
```

- **목록:** 길어질 수 있는 목록은 `{ items, total, nextCursor }` 모양이고, 다음 페이지는 `?cursor=`로 요청합니다.

## 주소 한눈에 보기

| 요청 | 주소 | 쓰는 화면 |
| --- | --- | --- |
| 분석 시작 | `POST /api/analyses` | 01 저장소 입력, 01-오류 |
| 최근 분석 목록 | `GET /api/repositories/recent` | 01 |
| 작업 상태 | `GET /api/jobs/{jobId}` | 02 분석 대기, 02-오류 |
| 진행률 실시간 | `GET /api/jobs/{jobId}/events` (SSE) | 02 |
| 실패 단계부터 다시 | `POST /api/jobs/{jobId}/retry` | 02-오류 |
| 지도 데이터 | `GET /api/jobs/{jobId}/graph` | 03 지도, 03-로딩 |
| 커밋 막대 | `GET /api/jobs/{jobId}/timeline` | 03 시간 되감기 |
| 어긋남 목록 | `GET /api/jobs/{jobId}/divergences` | 03, 03-빈 상태 |
| 어긋남 상세 | `GET /api/jobs/{jobId}/divergences/{id}` | 04 코드 비교 |
| 판단 기록 | `PUT` · `DELETE /api/divergences/{id}/verdict` | 04 |
| 함수 정보 | `GET /api/jobs/{jobId}/nodes/{nodeId}` | 03-선택 |
| 함수 소스 | `GET /api/jobs/{jobId}/nodes/{nodeId}/source` | 03-선택 "코드 보기" |
| 함수 찾기 | `GET /api/jobs/{jobId}/search?q=` | 03-검색 |
| 공유 링크 만들기 | `POST /api/jobs/{jobId}/shares` | 05 공유 |
| 공유 링크 열기 | `GET /api/shares/{token}` | 공유받은 사람 |

`nodeId`에는 `/`와 `:`가 들어가므로 주소에 넣을 때 `encodeURIComponent`로 감쌉니다.

## 분석 시작과 진행

### `POST /api/analyses`

```json
// 요청
{ "repo": "sample-store/commerce-core" }

// 201 응답. 같은 커밋을 이미 분석했으면 cached: true, status: "DONE"
{
  "jobId": "j_8f2a",
  "repository": { "id": "r_12", "owner": "sample-store", "name": "commerce-core", "url": "https://github.com/sample-store/commerce-core" },
  "status": "QUEUED",
  "cached": false
}
```

| 오류 코드 | HTTP | 01-오류 화면 문구 |
| --- | --- | --- |
| `INVALID_URL` | 400 | GitHub 저장소 주소가 아니에요 |
| `REPO_NOT_FOUND` | 404 | 이 저장소를 열 수 없어요 (비공개이거나 주소가 틀림) |
| `UNSUPPORTED_LANGUAGE` | 422 | Java·Python 파일을 찾지 못했어요 |
| `REPO_TOO_LARGE` | 413 | 저장소가 너무 커요 (500MB 초과) |

### `GET /api/jobs/{jobId}`

02 화면을 처음 열거나 새로고침할 때 현재 상태를 한 번에 받습니다. 이후 변화는 SSE로 받습니다.

```json
{
  "jobId": "j_8f2a",
  "repository": { "id": "r_12", "owner": "sample-store", "name": "commerce-core", "url": "https://github.com/sample-store/commerce-core" },
  "commit": { "sha": "a3f9c1e", "branch": "main", "date": "2026-10-28T09:12:00Z" },
  "status": "RUNNING",
  "stage": "SEMANTIC",
  "stages": [
    { "stage": "INGEST", "status": "DONE", "percent": 100, "detail": "커밋 2,000개를 받고 대량 커밋 37개는 뺐어요", "metrics": { "commits": 2000, "bulkExcluded": 37 } },
    { "stage": "STRUCTURE", "status": "DONE", "percent": 100, "detail": "함수 2,418개, 호출 관계 1,284개, 해석 성공률 87%", "metrics": { "functions": 2418, "edges": 1284, "resolvedRate": 0.87 } },
    { "stage": "SEMANTIC", "status": "RUNNING", "percent": 64, "detail": "함수 2,418개 중 1,546개 임베딩", "metrics": { "embedded": 1546, "total": 2418 } },
    { "stage": "HISTORY", "status": "PENDING", "percent": 0, "detail": null, "metrics": {} },
    { "stage": "DIVERGENCE", "status": "PENDING", "percent": 0, "detail": null, "metrics": {} }
  ],
  "startedAt": "2026-11-04T05:02:00Z",
  "finishedAt": null,
  "failure": null
}
```

실패하면 `status: "FAILED"`, 해당 단계 `status: "FAILED"`, 뒤 단계는 `CANCELLED`가 되고 `failure`가 채워집니다.

```json
"failure": { "stage": "SEMANTIC", "code": "OUT_OF_MEMORY", "message": "1,546번째 함수에서 메모리가 부족해 멈췄어요", "resumable": true }
```

### `GET /api/jobs/{jobId}/events` (SSE)

`text/event-stream`. 이벤트 이름이 `type`과 같고, `data`는 `JobEvent` JSON입니다. 다시 연결할 때 `Last-Event-ID`를 보내면 놓친 이벤트부터 받습니다.

```
event: stage
id: 41
data: {"type":"stage","stage":{"stage":"SEMANTIC","status":"RUNNING","percent":65,"detail":"함수 2,418개 중 1,572개 임베딩","metrics":{"embedded":1572,"total":2418}}}

event: done
id: 57
data: {"type":"done","jobId":"j_8f2a"}
```

### `POST /api/jobs/{jobId}/retry`

`failure.resumable`이 `true`일 때만 됩니다. 응답은 `Job`이며, 실패한 단계부터 다시 `RUNNING`이 됩니다.

## 지도

### `GET /api/jobs/{jobId}/graph`

분석이 끝나기 전에 요청하면 `409 JOB_NOT_READY`입니다.

```json
{
  "jobId": "j_8f2a",
  "stats": { "functions": 2418, "files": 312, "commits": 2000 },
  "modules": [ { "id": "billing/", "label": "billing", "hubNodeId": "billing/invoice.py::InvoiceService.create" } ],
  "nodes": [
    {
      "id": "billing/invoice.py::calc_total",
      "name": "calc_total",
      "path": "billing/invoice.py",
      "moduleId": "billing/",
      "kind": "function",
      "lines": [41, 50],
      "degree": 7,
      "semanticPosition": [0.42, -1.3, 2.05]
    }
  ],
  "edges": [
    { "source": "orders/service.py::place_order", "target": "billing/invoice.py::calc_total", "kind": "call", "weight": 2 },
    { "source": "billing/invoice.py::calc_total", "target": "orders/cart.py::sum_items", "kind": "similar", "weight": 0.92 },
    { "source": "auth/session.py::refresh", "target": "notify/mailer.py::render_template", "kind": "cochange", "weight": 0.71, "since": "2025-06-02T00:00:00Z" }
  ]
}
```

- **폴더별 보기 좌표**는 서버가 주지 않습니다. 프론트가 구조 엣지(call·import)로 force 레이아웃을 돌려 계산합니다(개발 플랜 Phase 6).
- **하는 일별 보기 좌표**는 `semanticPosition`(UMAP 3D)입니다.
- **선 종류와 지도:** `call`·`import` = 구조(흰 실선), `similar` = 의미(파란 점선), `cochange` = 역사(코랄 곡선).

### `GET /api/jobs/{jobId}/timeline`

```json
{ "from": "2024-03-01T00:00:00Z", "to": "2026-10-28T00:00:00Z", "buckets": [ { "date": "2024-03-04T00:00:00Z", "commits": 12 } ] }
```

시간 되감기는 이 막대와 `cochange` 엣지의 `since`로 그립니다.

## 어긋남

### `GET /api/jobs/{jobId}/divergences`

쿼리: `type`, `minScore`(기본 60), `limit`, `cursor`. 응답의 `minScore`는 실제로 적용된 기준이고, 03-빈 상태 문구("지금 기준(의심도 60 이상)")에 씁니다.

```json
{
  "items": [
    {
      "id": "d_01",
      "rank": 1,
      "type": "duplicate",
      "score": 92,
      "source": "billing/invoice.py::calc_total",
      "target": "orders/cart.py::sum_items",
      "moduleId": null,
      "summary": "orders/cart.py::sum_items",
      "evidence": { "similarity": 0.92, "structuralDistance": null, "cochangeCount": 0, "changeCounts": { "source": 23, "target": 17 } },
      "verdict": null
    },
    {
      "id": "d_04",
      "rank": 4,
      "type": "mixed_responsibility",
      "score": 79,
      "source": "orders/service.py::OrderService",
      "target": null,
      "moduleId": "orders/service.py",
      "summary": "결제, 재고, 알림 로직이 한 모듈에",
      "evidence": { "similarity": null, "structuralDistance": 1, "cochangeCount": 0, "changeCounts": { "source": 31, "target": null } },
      "verdict": null
    }
  ],
  "total": 47,
  "nextCursor": "c_20",
  "minScore": 60
}
```

- **의심도(`score`)는 0~100 정수**, **유사도(`similarity`)는 0~1 소수**입니다. 화면에서 둘이 섞이지 않게 단위를 다르게 둡니다.
- `structuralDistance: null`은 "호출 연결 없음"(4단계 안에 경로 없음)입니다.

### `GET /api/jobs/{jobId}/divergences/{id}`

`Divergence`에 04 화면용 필드가 붙습니다.

```json
{
  "...": "Divergence 필드 전부",
  "sourceCode": { "nodeId": "billing/invoice.py::calc_total", "path": "billing/invoice.py", "lines": [40, 51], "language": "python", "code": "def calc_total(invoice, tax_rate):\n    ...", "changeCount": 23, "lastModified": "2026-09-14T00:00:00Z" },
  "targetCode": { "nodeId": "orders/cart.py::sum_items", "path": "orders/cart.py", "lines": [111, 121], "language": "python", "code": "def sum_items(cart, region):\n    ...", "changeCount": 17, "lastModified": "2026-10-02T00:00:00Z" },
  "similarRanges": [ { "source": [44, 48], "target": [114, 118] } ],
  "similarSummary": "반복문 → 단가 × 수량 → 할인 적용 → 누적 구조가 같고, 변수명만 다릅니다",
  "cochangeCommits": [],
  "similarNodes": [ { "nodeId": "catalog/price.py::line_total", "similarity": 0.81 } ]
}
```

### `PUT /api/divergences/{id}/verdict`

```json
// 요청
{ "verdict": "real", "memo": "할인 계산을 pricing 모듈로 합치기" }
// 200 응답
{ "divergenceId": "d_01", "verdict": "real", "memo": "할인 계산을 pricing 모듈로 합치기", "updatedAt": "2026-11-04T06:10:00Z" }
```

`DELETE`는 판단을 지웁니다(204). 판단 버튼을 다시 누르면 취소되는 동작에 씁니다.

## 함수 정보와 찾기

### `GET /api/jobs/{jobId}/nodes/{nodeId}`

```json
{
  "node": { "id": "api/router.py::dispatch", "name": "dispatch", "path": "api/router.py", "moduleId": "api/", "kind": "function", "lines": [12, 58], "degree": 15, "semanticPosition": [1.1, 0.2, -0.7] },
  "lastModified": "2026-10-21T00:00:00Z",
  "counts": { "calls": 6, "calledBy": 9, "similar": 3, "cochanged": 4 },
  "divergences": [],
  "linked": [ { "nodeId": "notify/mailer.py::send", "relation": "cochange", "count": 4 } ]
}
```

### `GET /api/jobs/{jobId}/nodes/{nodeId}/source`

응답은 `SourceCode` 하나입니다.

### `GET /api/jobs/{jobId}/search?q=send&limit=10`

```json
{
  "functions": [ { "nodeId": "notify/mailer.py::send", "path": "notify/mailer.py", "name": "send", "degree": 5, "divergenceCount": 1, "match": [18, 22] } ],
  "files": [ { "path": "notify/sender.py", "functionCount": 6, "match": [7, 11] } ]
}
```

`match`는 `nodeId`(파일은 `path`) 안에서 검색어와 맞는 구간 `[시작, 끝)`입니다. 화면은 이 구간을 굵게 칠합니다.

## 공유

### `POST /api/jobs/{jobId}/shares`

```json
// 요청
{
  "view": {
    "layout": "structure",
    "layers": { "structure": true, "semantic": true, "history": true },
    "camera": { "position": [0, 0, 8], "target": [0.4, -0.2, 0] },
    "focus": { "divergenceId": "d_01" },
    "timelineAt": null
  },
  "visibility": "public",
  "expiresInDays": 30
}
// 201 응답
{ "token": "k3Fq9x", "url": "https://codemap.app/s/k3Fq9x", "jobId": "j_8f2a", "commit": { "sha": "a3f9c1e", "branch": "main", "date": "2026-10-28T09:12:00Z" }, "view": { "...": "요청과 같음" }, "visibility": "public", "expiresAt": "2026-12-04T06:20:00Z" }
```

### `GET /api/shares/{token}`

로그인 없이 됩니다. 응답은 `Share`이고, 프론트는 `jobId`의 지도를 `view` 상태로 엽니다. 만료됐으면 `404 NOT_FOUND`입니다.

## 아직 정하지 않은 것

- **로그인 방식:** 플랜은 "간단한 이메일 로그인으로 시작"입니다. 주소(`/api/auth/...`)는 백엔드 Phase 1에서 정합니다.
- **큰 저장소의 지도 크기:** 함수가 수천 개면 `graph` 응답이 수 MB가 됩니다. 성능 측정(Phase 6) 결과를 보고 `edges`를 종류별로 나눠 받을지(`?kinds=`) 정합니다.
- **팀 공개 범위:** `visibility: "team"`의 "팀"이 무엇인지는 로그인 방식과 함께 정합니다.
