import type {
  CreateAnalysisResponse,
  CreateShareRequest,
  DivergenceDetail,
  DivergencePage,
  DivergenceQuery,
  ErrorCode,
  Graph,
  Job,
  JobEvent,
  NodeDetail,
  NodeId,
  RecentAnalysis,
  SearchResult,
  Share,
  SourceCode,
  Timeline,
  VerdictRequest,
  VerdictResponse,
} from './types'

/** 서버가 ApiError 본문으로 응답했을 때 던지는 오류 */
export class ApiRequestError extends Error {
  readonly code: ErrorCode
  readonly status: number
  readonly hint?: string

  constructor(status: number, code: ErrorCode, message: string, hint?: string) {
    super(message)
    this.status = status
    this.code = code
    this.hint = hint
  }
}

/** docs/API_CONTRACT.md 의 주소 하나가 메서드 하나다 */
export interface CodemapApi {
  createAnalysis(repo: string): Promise<CreateAnalysisResponse>
  recentAnalyses(): Promise<RecentAnalysis[]>
  getJob(jobId: string): Promise<Job>
  /** 진행 이벤트를 구독한다. 반환값을 호출하면 구독을 끊는다 */
  subscribeJob(jobId: string, onEvent: (event: JobEvent) => void): () => void
  retryJob(jobId: string): Promise<Job>
  getGraph(jobId: string): Promise<Graph>
  getTimeline(jobId: string): Promise<Timeline>
  listDivergences(jobId: string, query?: DivergenceQuery): Promise<DivergencePage>
  getDivergence(jobId: string, divergenceId: string): Promise<DivergenceDetail>
  setVerdict(divergenceId: string, body: VerdictRequest): Promise<VerdictResponse>
  clearVerdict(divergenceId: string): Promise<void>
  getNode(jobId: string, nodeId: NodeId): Promise<NodeDetail>
  getSource(jobId: string, nodeId: NodeId): Promise<SourceCode>
  search(jobId: string, q: string, limit?: number): Promise<SearchResult>
  createShare(jobId: string, body: CreateShareRequest): Promise<Share>
  getShare(token: string): Promise<Share>
}
