import type { CodemapApi } from './client'
import { httpApi } from './http'
import { adoptJob, mockApi } from './mock/mockApi'

/**
 * VITE_API=http   전부 실제 백엔드
 * VITE_API=hybrid 백엔드에 있는 것(analyses, jobs, events, retry, graph)만 실제로, 나머지는 mock
 * 그 외           전부 브라우저 안의 가짜 API
 */
const hybridApi: CodemapApi = {
  ...mockApi,
  createAnalysis: httpApi.createAnalysis,
  getJob: httpApi.getJob,
  subscribeJob: httpApi.subscribeJob,
  retryJob: httpApi.retryJob,
  getGraph: httpApi.getGraph,
  // 아래는 아직 백엔드에 없다. 실제 작업 ID로 불려도 mock이 동작하게 등록해 준다.
  getTimeline: (jobId) => (adoptJob(jobId), mockApi.getTimeline(jobId)),
  listDivergences: (jobId, query) => (adoptJob(jobId), mockApi.listDivergences(jobId, query)),
  getDivergence: (jobId, id) => (adoptJob(jobId), mockApi.getDivergence(jobId, id)),
  getNode: (jobId, nodeId) => (adoptJob(jobId), mockApi.getNode(jobId, nodeId)),
  getSource: (jobId, nodeId) => (adoptJob(jobId), mockApi.getSource(jobId, nodeId)),
  search: (jobId, q, limit) => (adoptJob(jobId), mockApi.search(jobId, q, limit)),
  createShare: (jobId, body) => (adoptJob(jobId), mockApi.createShare(jobId, body)),
}

const mode = import.meta.env.VITE_API
export const api: CodemapApi = mode === 'http' ? httpApi : mode === 'hybrid' ? hybridApi : mockApi

export { ApiRequestError } from './client'
export * from './types'
