// API 계약. 백엔드 DTO와 가짜 데이터(mock)는 이 타입을 기준으로 맞춘다.
// 설명과 예시는 docs/API_CONTRACT.md

/** ISO 8601 날짜·시간 문자열 (예: "2026-10-28T14:02:00Z") */
export type IsoDateTime = string

/** 함수 노드 ID: "파일경로::클래스.함수" 또는 "파일경로::함수" */
export type NodeId = string

export type Vec3 = [number, number, number]

/** 시작 줄, 끝 줄 (1부터, 끝 줄 포함) */
export type LineRange = [number, number]

// ---------- 공통 ----------

export type ErrorCode =
  | 'INVALID_URL'
  | 'REPO_NOT_FOUND'
  | 'UNSUPPORTED_LANGUAGE'
  | 'REPO_TOO_LARGE'
  | 'JOB_NOT_FOUND'
  | 'JOB_NOT_READY'
  | 'NOT_FOUND'
  | 'UNAUTHORIZED'
  | 'INTERNAL'

/** 4xx·5xx 응답 본문 */
export interface ApiError {
  error: {
    code: ErrorCode
    /** 사용자에게 그대로 보여줄 수 있는 한국어 문장 */
    message: string
    /** 해결 방법 안내 (선택) */
    hint?: string
  }
}

export interface Page<T> {
  items: T[]
  total: number
  /** 다음 페이지가 없으면 null */
  nextCursor: string | null
}

// ---------- 저장소와 분석 작업 ----------

export interface Repository {
  id: string
  owner: string
  name: string
  /** https://github.com/owner/name */
  url: string
}

export interface CommitRef {
  sha: string
  branch: string
  date: IsoDateTime
}

export type JobStatus = 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED'

/** 분석 5단계: 수집 → 구조 → 의미 → 역사 → 어긋남 탐지 */
export type StageName = 'INGEST' | 'STRUCTURE' | 'SEMANTIC' | 'HISTORY' | 'DIVERGENCE'

export type StageStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED' | 'CANCELLED'

export interface Stage {
  stage: StageName
  status: StageStatus
  /** 0~100 */
  percent: number
  /** 화면에 그대로 쓰는 한 줄 설명 (예: "커밋 2,000개를 받고 대량 커밋 37개는 뺐어요") */
  detail: string | null
  /** 단계별 수치. 키는 단계마다 다르다 (예: functions, edges, resolvedRate) */
  metrics: Record<string, number>
}

export interface JobFailure {
  stage: StageName
  code: string
  message: string
  /** true면 실패한 단계부터 다시 시도할 수 있다 */
  resumable: boolean
}

export interface Job {
  jobId: string
  repository: Repository
  commit: CommitRef | null
  status: JobStatus
  /** 지금 진행 중이거나 마지막으로 진행한 단계 */
  stage: StageName | null
  stages: Stage[]
  startedAt: IsoDateTime | null
  finishedAt: IsoDateTime | null
  failure: JobFailure | null
}

/** POST /api/analyses */
export interface CreateAnalysisRequest {
  /** "owner/name" 또는 GitHub 전체 URL */
  repo: string
}

export interface CreateAnalysisResponse {
  jobId: string
  repository: Repository
  status: JobStatus
  /** 같은 커밋을 이미 분석했으면 true. 이때 status는 DONE */
  cached: boolean
}

/** GET /api/repositories/recent 의 한 줄 */
export interface RecentAnalysis {
  repository: Repository
  jobId: string
  commit: CommitRef
  functionCount: number
  divergenceCount: number
  finishedAt: IsoDateTime
}

// ---------- 진행률 SSE (GET /api/jobs/{jobId}/events) ----------

export type JobEvent =
  | { type: 'stage'; stage: Stage }
  | { type: 'done'; jobId: string }
  | { type: 'failed'; failure: JobFailure }

// ---------- 지도 ----------

export interface Module {
  /** 폴더 경로, 예: "billing/" */
  id: string
  label: string
  /** 폴더 대표 함수 (연결이 가장 많은 함수) */
  hubNodeId: NodeId
}

export type NodeKind = 'function' | 'method'

export interface GraphNode {
  id: NodeId
  /** 표시용 짧은 이름, 예: "calc_total" 또는 "Router.dispatch" */
  name: string
  path: string
  moduleId: string
  kind: NodeKind
  lines: LineRange
  /** 구조 엣지(호출·import) 기준 연결 수 */
  degree: number
  /** 하는 일별 보기 좌표 (UMAP 3D). 폴더별 보기 좌표는 프론트가 force 레이아웃으로 계산한다 */
  semanticPosition: Vec3
}

/** call·import = 구조 지도, similar = 의미 지도, cochange = 역사 지도 */
export type EdgeKind = 'call' | 'import' | 'similar' | 'cochange'

export type MapLayer = 'structure' | 'semantic' | 'history'

export interface GraphEdge {
  source: NodeId
  target: NodeId
  kind: EdgeKind
  /**
   * call·import: 호출 횟수(정적), similar: 코사인 유사도 0~1,
   * cochange: 함께 수정 신뢰도 0~1
   */
  weight: number
  /** cochange만: 처음 함께 수정된 시점 (시간 되감기에 사용) */
  since?: IsoDateTime
}

export interface GraphStats {
  functions: number
  files: number
  commits: number
}

/** GET /api/jobs/{jobId}/graph */
export interface Graph {
  jobId: string
  stats: GraphStats
  modules: Module[]
  nodes: GraphNode[]
  edges: GraphEdge[]
}

/** GET /api/jobs/{jobId}/timeline */
export interface Timeline {
  from: IsoDateTime
  to: IsoDateTime
  /** 기간별 커밋 수 (막대 그래프) */
  buckets: { date: IsoDateTime; commits: number }[]
}

// ---------- 어긋남 ----------

/** duplicate = 중복 구현, hidden_coupling = 숨은 결합, mixed_responsibility = 책임 혼재 */
export type DivergenceType = 'duplicate' | 'hidden_coupling' | 'mixed_responsibility'

export type Verdict = 'real' | 'false_positive'

export interface CochangeCommit {
  sha: string
  date: IsoDateTime
  message: string
}

export interface DivergenceEvidence {
  /** 하는 일 유사도 0~1 */
  similarity: number | null
  /** 호출 관계로 몇 단계 떨어졌나. null이면 4단계 안에 연결 없음 */
  structuralDistance: number | null
  cochangeCount: number
  /** 각 함수가 수정된 횟수 */
  changeCounts: { source: number; target: number | null }
}

export interface Divergence {
  id: string
  /** 의심도 순위, 1부터 */
  rank: number
  type: DivergenceType
  /** 의심도 0~100 */
  score: number
  source: NodeId
  /** 책임 혼재는 짝이 없으므로 null */
  target: NodeId | null
  /** 책임 혼재만: 대상 폴더(파일) 경로 */
  moduleId: string | null
  /** 목록 둘째 줄에 쓰는 한 줄 요약 */
  summary: string
  evidence: DivergenceEvidence
  verdict: Verdict | null
}

/** GET /api/jobs/{jobId}/divergences 쿼리 */
export interface DivergenceQuery {
  type?: DivergenceType
  /** 기본 60 */
  minScore?: number
  limit?: number
  cursor?: string
}

export interface DivergencePage extends Page<Divergence> {
  /** 이번 응답에 적용된 의심도 기준 (빈 상태 문구에 사용) */
  minScore: number
}

export interface SourceCode {
  nodeId: NodeId
  path: string
  lines: LineRange
  language: 'java' | 'python'
  code: string
  changeCount: number
  lastModified: IsoDateTime
}

/** GET /api/jobs/{jobId}/divergences/{id} */
export interface DivergenceDetail extends Divergence {
  sourceCode: SourceCode
  targetCode: SourceCode | null
  /** 두 소스에서 비슷한 줄 범위 짝 (파일 기준 줄 번호) */
  similarRanges: { source: LineRange; target: LineRange }[]
  /** 유사 구간 한 줄 요약, 예: "반복문 → 단가 × 수량 → 할인 적용 → 누적 구조가 같고, 변수명만 다릅니다" */
  similarSummary: string | null
  cochangeCommits: CochangeCommit[]
  /** source와 하는 일이 비슷한 다른 함수 */
  similarNodes: { nodeId: NodeId; similarity: number }[]
}

/** PUT /api/divergences/{id}/verdict */
export interface VerdictRequest {
  verdict: Verdict
  memo?: string
}

export interface VerdictResponse {
  divergenceId: string
  verdict: Verdict
  memo: string | null
  updatedAt: IsoDateTime
}

// ---------- 함수 정보와 검색 ----------

export type LinkRelation = 'calls' | 'called_by' | 'cochange' | 'similar'

/** GET /api/jobs/{jobId}/nodes/{nodeId} */
export interface NodeDetail {
  node: GraphNode
  lastModified: IsoDateTime
  counts: { calls: number; calledBy: number; similar: number; cochanged: number }
  divergences: Divergence[]
  linked: { nodeId: NodeId; relation: LinkRelation; count: number }[]
}

/** GET /api/jobs/{jobId}/search?q= */
export interface SearchResult {
  functions: {
    nodeId: NodeId
    path: string
    name: string
    degree: number
    divergenceCount: number
    /** 이름(nodeId) 안에서 검색어와 맞는 부분 [시작, 끝) */
    match: [number, number]
  }[]
  files: { path: string; functionCount: number; match: [number, number] }[]
}

// ---------- 공유 링크 ----------

export type LayoutMode = 'structure' | 'semantic'

export interface ViewState {
  layout: LayoutMode
  layers: Record<MapLayer, boolean>
  camera: { position: Vec3; target: Vec3 }
  focus: { divergenceId: string } | { nodeId: NodeId } | null
  /** 시간 되감기 위치. null이면 최신 */
  timelineAt: IsoDateTime | null
}

/** POST /api/jobs/{jobId}/shares */
export interface CreateShareRequest {
  view: ViewState
  visibility: 'public' | 'team'
  expiresInDays: number
}

export interface Share {
  token: string
  url: string
  jobId: string
  commit: CommitRef
  view: ViewState
  visibility: 'public' | 'team'
  expiresAt: IsoDateTime
}
