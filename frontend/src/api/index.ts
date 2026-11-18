import type { CodemapApi } from './client'
import { httpApi } from './http'
import { adoptJob, mockApi } from './mock/mockApi'
import type { Graph } from './types'

/**
 * VITE_API=http   전부 실제 백엔드
 * VITE_API=hybrid 백엔드에 있는 것(analyses, jobs, events, retry, graph)만 실제로, 나머지는 mock
 * 그 외           전부 브라우저 안의 가짜 API
 */

// 실제 그래프를 한 번만 받아서 mock이 기준으로 삼게 한다 (노드 상세·검색·어긋남이 실제 함수를 가리키도록)
const realGraphs = new Map<string, Promise<Graph>>()

async function adopt(jobId: string): Promise<void> {
  let graph = realGraphs.get(jobId)
  if (!graph) {
    graph = httpApi.getGraph(jobId)
    realGraphs.set(jobId, graph)
    graph.catch(() => realGraphs.delete(jobId)) // 아직 끝나지 않은 작업 등은 다음에 다시 시도한다
  }
  adoptJob(jobId, await graph)
}

/** mock 엔드포인트를 부르기 전에 실제 그래프를 등록한다 */
const withRealGraph =
  <A extends unknown[], R>(fn: (jobId: string, ...args: A) => Promise<R>) =>
  async (jobId: string, ...args: A): Promise<R> => {
    await adopt(jobId)
    return fn(jobId, ...args)
  }

const hybridApi: CodemapApi = {
  ...mockApi,
  createAnalysis: httpApi.createAnalysis,
  getJob: httpApi.getJob,
  subscribeJob: httpApi.subscribeJob,
  retryJob: httpApi.retryJob,
  getGraph: httpApi.getGraph,
  // 아래는 아직 백엔드에 없다
  getTimeline: withRealGraph(mockApi.getTimeline),
  listDivergences: withRealGraph(mockApi.listDivergences),
  getDivergence: withRealGraph(mockApi.getDivergence),
  getNode: withRealGraph(mockApi.getNode),
  getSource: withRealGraph(mockApi.getSource),
  search: withRealGraph(mockApi.search),
  createShare: withRealGraph(mockApi.createShare),
}

const mode = import.meta.env.VITE_API
export const api: CodemapApi = mode === 'http' ? httpApi : mode === 'hybrid' ? hybridApi : mockApi

export { ApiRequestError } from './client'
export * from './types'
