import { ApiRequestError, type CodemapApi } from './client'
import type { ApiError, JobEvent } from './types'

const base = '/api'

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = localStorage.getItem('codemap.token')
  const res = await fetch(base + path, {
    method,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as ApiError | null
    const e = data?.error
    throw new ApiRequestError(res.status, e?.code ?? 'INTERNAL', e?.message ?? '요청을 처리하지 못했어요', e?.hint)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

const enc = encodeURIComponent

/** 실제 백엔드(Spring Boot)에 붙는 구현 */
export const httpApi: CodemapApi = {
  createAnalysis: (repo) => request('POST', '/analyses', { repo }),
  recentAnalyses: () => request('GET', '/repositories/recent'),
  getJob: (jobId) => request('GET', `/jobs/${enc(jobId)}`),
  subscribeJob(jobId, onEvent) {
    const source = new EventSource(`${base}/jobs/${enc(jobId)}/events`)
    for (const type of ['stage', 'done', 'failed'] as const) {
      source.addEventListener(type, (e) => onEvent(JSON.parse((e as MessageEvent).data) as JobEvent))
    }
    return () => source.close()
  },
  retryJob: (jobId) => request('POST', `/jobs/${enc(jobId)}/retry`),
  getGraph: (jobId) => request('GET', `/jobs/${enc(jobId)}/graph`),
  getTimeline: (jobId) => request('GET', `/jobs/${enc(jobId)}/timeline`),
  listDivergences(jobId, query = {}) {
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(query)) if (v !== undefined) params.set(k, String(v))
    const qs = params.toString()
    return request('GET', `/jobs/${enc(jobId)}/divergences${qs ? `?${qs}` : ''}`)
  },
  getDivergence: (jobId, id) => request('GET', `/jobs/${enc(jobId)}/divergences/${enc(id)}`),
  setVerdict: (id, body) => request('PUT', `/divergences/${enc(id)}/verdict`, body),
  clearVerdict: (id) => request('DELETE', `/divergences/${enc(id)}/verdict`),
  getNode: (jobId, nodeId) => request('GET', `/jobs/${enc(jobId)}/nodes/${enc(nodeId)}`),
  getSource: (jobId, nodeId) => request('GET', `/jobs/${enc(jobId)}/nodes/${enc(nodeId)}/source`),
  search: (jobId, q, limit = 10) => request('GET', `/jobs/${enc(jobId)}/search?q=${enc(q)}&limit=${limit}`),
  createShare: (jobId, body) => request('POST', `/jobs/${enc(jobId)}/shares`, body),
  getShare: (token) => request('GET', `/shares/${enc(token)}`),
}
