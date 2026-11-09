// 브라우저 안에서 동작하는 가짜 API. 저장소 이름으로 상황을 고른다.
//   sample-store/commerce-core 등 최근 목록의 저장소 → 이미 분석됨(바로 지도)
//   이름에 private      → REPO_NOT_FOUND
//   이름에 flaky        → 의미 지도 64%에서 실패, 다시 시도하면 이어서 진행
//   이름에 tidy         → 분석은 끝나지만 어긋남 0건
//   그 밖의 owner/name  → 약 8초 동안 5단계를 진행한 뒤 완료
import { ApiRequestError, type CodemapApi } from '../client'
import type { Divergence, Graph, Job, JobEvent, Repository, Share, Stage, StageName } from '../types'
import { buildGraph, divergencesFor, sourceFor, timelineFor } from './fixtures'

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const latency = () => sleep(150 + Math.random() * 250)

const STAGES: StageName[] = ['INGEST', 'STRUCTURE', 'SEMANTIC', 'HISTORY', 'DIVERGENCE']
const DURATION: Record<StageName, number> = { INGEST: 1200, STRUCTURE: 1600, SEMANTIC: 3000, HISTORY: 1400, DIVERGENCE: 1000 }
const DONE_DETAIL: Record<StageName, string> = {
  INGEST: '커밋 2,000개를 받고 대량 커밋 37개는 뺐어요',
  STRUCTURE: '함수 2,418개, 호출 관계 1,284개, 해석 성공률 87%',
  SEMANTIC: '함수 2,418개 임베딩 완료',
  HISTORY: '같이 수정된 함수 쌍 862개',
  DIVERGENCE: '어긋남 9개',
}
const runningDetail = (s: StageName, p: number) => {
  switch (s) {
    case 'INGEST': return `커밋 ${Math.round(20 * p).toLocaleString()}개 받는 중`
    case 'STRUCTURE': return `함수 ${Math.round(24.18 * p).toLocaleString()}개 파싱`
    case 'SEMANTIC': return `함수 2,418개 중 ${Math.round(24.18 * p).toLocaleString()}개 임베딩`
    case 'HISTORY': return '같이 수정된 함수 쌍 계산'
    case 'DIVERGENCE': return '세 지도를 비교해 의심도 계산'
  }
}

interface JobRecord {
  job: Job
  failAt: number | null
  listeners: Set<(e: JobEvent) => void>
  timer?: ReturnType<typeof setInterval>
}

const jobs = new Map<string, JobRecord>()
const verdicts = new Map<string, { verdict: Divergence['verdict']; memo: string | null }>()
const shares = new Map<string, Share>()
const graphs = new Map<string, Graph>()
let seq = 0

const repoOf = (owner: string, name: string): Repository => ({ id: `r_${owner}_${name}`, owner, name, url: `https://github.com/${owner}/${name}` })
const commit = { sha: 'a3f9c1e', branch: 'main', date: '2026-10-28T09:12:00Z' }

function doneJob(jobId: string, repo: Repository): Job {
  return {
    jobId, repository: repo, commit, status: 'DONE', stage: 'DIVERGENCE',
    stages: STAGES.map((stage) => ({ stage, status: 'DONE', percent: 100, detail: DONE_DETAIL[stage], metrics: {} })),
    startedAt: '2026-10-28T09:20:00Z', finishedAt: '2026-10-28T09:28:00Z', failure: null,
  }
}

const RECENT = [
  { jobId: 'j_demo', repo: repoOf('sample-store', 'commerce-core'), finishedAt: '2026-10-28T09:28:00Z' },
  { jobId: 'j_pay', repo: repoOf('sample-store', 'payments-gateway'), finishedAt: '2026-10-21T11:02:00Z' },
  { jobId: 'j_inv', repo: repoOf('sample-store', 'inventory-svc'), finishedAt: '2026-10-14T16:40:00Z' },
]
for (const r of RECENT) jobs.set(r.jobId, { job: doneJob(r.jobId, r.repo), failAt: null, listeners: new Set() })

function record(jobId: string): JobRecord {
  const rec = jobs.get(jobId)
  if (!rec) throw new ApiRequestError(404, 'JOB_NOT_FOUND', '분석 작업을 찾지 못했어요')
  return rec
}

function emit(rec: JobRecord, e: JobEvent) { for (const l of rec.listeners) l(e) }

function run(rec: JobRecord) {
  const { job } = rec
  job.status = 'RUNNING'
  job.startedAt ??= new Date().toISOString()
  const tick = 150
  rec.timer = setInterval(() => {
    const i = job.stages.findIndex((s) => s.status === 'PENDING' || s.status === 'RUNNING')
    if (i < 0) {
      clearInterval(rec.timer)
      job.status = 'DONE'
      job.finishedAt = new Date().toISOString()
      emit(rec, { type: 'done', jobId: job.jobId })
      return
    }
    const s = job.stages[i]
    job.stage = s.stage
    s.status = 'RUNNING'
    s.percent = Math.min(100, s.percent + (100 * tick) / DURATION[s.stage])
    if (rec.failAt !== null && s.stage === 'SEMANTIC' && s.percent >= rec.failAt) {
      clearInterval(rec.timer)
      s.percent = rec.failAt
      s.status = 'FAILED'
      s.detail = '1,546번째 함수에서 메모리가 부족해 멈췄어요'
      for (const later of job.stages.slice(i + 1)) later.status = 'CANCELLED'
      job.status = 'FAILED'
      job.failure = { stage: 'SEMANTIC', code: 'OUT_OF_MEMORY', message: '1,546번째 함수에서 메모리가 부족해 멈췄어요', resumable: true }
      emit(rec, { type: 'stage', stage: { ...s } })
      emit(rec, { type: 'failed', failure: job.failure })
      return
    }
    if (s.percent >= 100) { s.status = 'DONE'; s.detail = DONE_DETAIL[s.stage] } else s.detail = runningDetail(s.stage, s.percent)
    emit(rec, { type: 'stage', stage: { ...s } })
  }, tick)
}

function parseRepo(input: string) {
  const m = input.trim().replace(/\.git$/, '').match(/^(?:https?:\/\/)?(?:www\.)?(?:github\.com\/)?([\w.-]+)\/([\w.-]+)\/?$/)
  return m ? { owner: m[1], name: m[2] } : null
}

function graphOf(jobId: string) {
  let g = graphs.get(jobId)
  if (!g) { g = buildGraph(jobId); graphs.set(jobId, g) }
  return g
}

function divergencesOf(jobId: string): Divergence[] {
  return divergencesFor(jobId).map((d) => ({ ...d, verdict: verdicts.get(d.id)?.verdict ?? null }))
}

function ready(jobId: string) {
  if (record(jobId).job.status !== 'DONE') throw new ApiRequestError(409, 'JOB_NOT_READY', '아직 분석이 끝나지 않았어요')
}

export const mockApi: CodemapApi = {
  async createAnalysis(input) {
    await latency()
    const p = parseRepo(input)
    if (!p) throw new ApiRequestError(400, 'INVALID_URL', 'GitHub 저장소 주소가 아니에요', '예: github.com/owner/repo')
    if (p.name.includes('private')) throw new ApiRequestError(404, 'REPO_NOT_FOUND', '이 저장소를 열 수 없어요', '비공개 저장소이거나 주소가 틀렸을 수 있어요. 공개 저장소의 주소인지 확인해 주세요. 예: github.com/owner/repo')
    const cached = RECENT.find((r) => r.repo.owner === p.owner && r.repo.name === p.name)
    if (cached) return { jobId: cached.jobId, repository: cached.repo, status: 'DONE', cached: true }
    const repo = repoOf(p.owner, p.name)
    const jobId = `${p.name.includes('tidy') ? 'j_tidy' : 'j'}_${++seq}`
    const stages: Stage[] = STAGES.map((stage) => ({ stage, status: 'PENDING', percent: 0, detail: null, metrics: {} }))
    const rec: JobRecord = { job: { jobId, repository: repo, commit, status: 'QUEUED', stage: null, stages, startedAt: null, finishedAt: null, failure: null }, failAt: p.name.includes('flaky') ? 64 : null, listeners: new Set() }
    jobs.set(jobId, rec)
    run(rec)
    return { jobId, repository: repo, status: 'QUEUED', cached: false }
  },
  async recentAnalyses() {
    await latency()
    return RECENT.map((r) => ({ repository: r.repo, jobId: r.jobId, commit, functionCount: graphOf(r.jobId).nodes.length, divergenceCount: divergencesFor(r.jobId).filter((d) => d.score >= 60).length, finishedAt: r.finishedAt }))
  },
  async getJob(jobId) {
    await latency()
    return structuredClone(record(jobId).job)
  },
  subscribeJob(jobId, onEvent) {
    const rec = jobs.get(jobId)
    if (!rec) return () => {}
    rec.listeners.add(onEvent)
    return () => rec.listeners.delete(onEvent)
  },
  async retryJob(jobId) {
    await latency()
    const rec = record(jobId)
    if (!rec.job.failure?.resumable) throw new ApiRequestError(409, 'JOB_NOT_READY', '다시 시도할 수 없는 작업이에요')
    rec.failAt = null
    rec.job.failure = null
    for (const s of rec.job.stages) if (s.status === 'FAILED' || s.status === 'CANCELLED') s.status = 'PENDING'
    run(rec)
    return structuredClone(rec.job)
  },
  async getGraph(jobId) { await latency(); ready(jobId); return graphOf(jobId) },
  async getTimeline(jobId) { await latency(); ready(jobId); return timelineFor(jobId) },
  async listDivergences(jobId, query = {}) {
    await latency(); ready(jobId)
    const minScore = query.minScore ?? 60
    const all = divergencesOf(jobId).filter((d) => d.score >= minScore && (!query.type || d.type === query.type))
    const start = query.cursor ? Number(query.cursor) : 0
    const limit = query.limit ?? 50
    const items = all.slice(start, start + limit)
    return { items, total: all.length, nextCursor: start + limit < all.length ? String(start + limit) : null, minScore }
  },
  async getDivergence(jobId, id) {
    await latency(); ready(jobId)
    const d = divergencesOf(jobId).find((x) => x.id === id)
    if (!d) throw new ApiRequestError(404, 'NOT_FOUND', '어긋남을 찾지 못했어요')
    const isFirst = d.id === 'd_01'
    return {
      ...d,
      sourceCode: sourceFor(d.source),
      targetCode: d.target ? sourceFor(d.target) : null,
      similarRanges: isFirst ? [{ source: [44, 48], target: [114, 118] }] : [],
      similarSummary: isFirst ? '반복문 → 단가 × 수량 → 할인 적용 → 누적 구조가 같고, 변수명만 다릅니다' : null,
      cochangeCommits: d.evidence.cochangeCount ? [{ sha: 'b71e0d2', date: '2026-09-30T00:00:00Z', message: '세션 갱신 시 알림 템플릿 변수 수정' }] : [],
      similarNodes: [{ nodeId: 'catalog/price.py::line_total', similarity: 0.81 }, { nodeId: 'api/export.py::sum_rows', similarity: 0.74 }, { nodeId: 'billing/refund.py::refund_amount', similarity: 0.7 }],
    }
  },
  async setVerdict(id, body) {
    await latency()
    verdicts.set(id, { verdict: body.verdict, memo: body.memo ?? null })
    return { divergenceId: id, verdict: body.verdict, memo: body.memo ?? null, updatedAt: new Date().toISOString() }
  },
  async clearVerdict(id) { await latency(); verdicts.delete(id) },
  async getNode(jobId, nodeId) {
    await latency(); ready(jobId)
    const g = graphOf(jobId)
    const node = g.nodes.find((n) => n.id === nodeId)
    if (!node) throw new ApiRequestError(404, 'NOT_FOUND', '함수를 찾지 못했어요')
    const out = g.edges.filter((e) => e.source === nodeId), inc = g.edges.filter((e) => e.target === nodeId)
    const count = (k: string, list = [...out, ...inc]) => list.filter((e) => e.kind === k).length
    return {
      node, lastModified: '2026-10-21T00:00:00Z',
      counts: { calls: count('call', out), calledBy: count('call', inc), similar: count('similar'), cochanged: count('cochange') },
      divergences: divergencesOf(jobId).filter((d) => d.source === nodeId || d.target === nodeId),
      linked: [...out.filter((e) => e.kind === 'call').map((e) => ({ nodeId: e.target, relation: 'calls' as const, count: e.weight })),
        ...[...out, ...inc].filter((e) => e.kind === 'cochange').map((e) => ({ nodeId: e.source === nodeId ? e.target : e.source, relation: 'cochange' as const, count: 4 }))].slice(0, 8),
    }
  },
  async getSource(jobId, nodeId) { await latency(); ready(jobId); return sourceFor(nodeId) },
  async search(jobId, q, limit = 10) {
    await sleep(80); ready(jobId)
    const needle = q.trim().toLowerCase()
    if (!needle) return { functions: [], files: [] }
    const g = graphOf(jobId)
    const divs = divergencesOf(jobId)
    const functions = g.nodes.filter((n) => n.id.toLowerCase().includes(needle)).slice(0, limit).map((n) => {
      const at = n.id.toLowerCase().indexOf(needle)
      return { nodeId: n.id, path: n.path, name: n.name, degree: n.degree, divergenceCount: divs.filter((d) => d.source === n.id || d.target === n.id).length, match: [at, at + needle.length] as [number, number] }
    })
    const paths = [...new Set(g.nodes.map((n) => n.path))].filter((p) => p.toLowerCase().includes(needle)).slice(0, 3)
    const files = paths.map((p) => { const at = p.toLowerCase().indexOf(needle); return { path: p, functionCount: g.nodes.filter((n) => n.path === p).length, match: [at, at + needle.length] as [number, number] } })
    return { functions, files }
  },
  async createShare(jobId, body) {
    await latency()
    const token = Math.random().toString(36).slice(2, 8)
    const share: Share = { token, url: `${location.origin}/s/${token}`, jobId, commit, view: body.view, visibility: body.visibility, expiresAt: new Date(Date.now() + body.expiresInDays * 864e5).toISOString() }
    shares.set(token, share)
    return share
  },
  async getShare(token) {
    await latency()
    const s = shares.get(token)
    if (!s) throw new ApiRequestError(404, 'NOT_FOUND', '공유 링크가 없거나 만료됐어요')
    return s
  },
}
