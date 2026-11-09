import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type DivergenceDetail, type Verdict } from '../../api'
import { TopBar } from '../../components/layout/TopBar'
import { Button } from '../../components/ui/Button'
import { ArrowLeftIcon } from '../../components/ui/icons'
import { DIVERGENCE_TYPE } from '../../lib/labels'
import { CodePane } from './CodePane'
import styles from './ComparePage.module.css'

const HEADLINE = {
  duplicate: '같은 로직이 서로 연결되지 않은 두 곳에 있습니다',
  hidden_coupling: '서로 부르지 않는데 늘 같이 고쳐집니다',
  mixed_responsibility: '한 모듈이 성격이 다른 일을 함께 맡고 있습니다',
} as const

function Metrics({ d }: { d: DivergenceDetail }) {
  const e = d.evidence
  const rows = [
    { map: '의미 · 하는 일', value: e.similarity === null ? '없음' : e.similarity.toFixed(2), ratio: e.similarity ?? 0, color: 'var(--color-map-semantic)',
      note: e.similarity === null ? '짝이 없는 어긋남이에요' : d.similarNodes.length ? `${d.source.split('::')[1]}과 하는 일이 비슷한 정도` : '' },
    { map: '구조 · 호출 관계', value: e.structuralDistance === null ? '연결 없음' : `${e.structuralDistance}단계`, ratio: e.structuralDistance === null ? 1 : e.structuralDistance / 4, color: 'var(--color-map-structure)',
      note: e.structuralDistance === null ? '호출이나 import로 4단계 안에 닿지 않음' : `호출을 따라 ${e.structuralDistance}단계 거리` },
    { map: '역사 · 수정 이력', value: `${e.cochangeCount}회`, ratio: Math.min(1, e.cochangeCount / 15), color: 'var(--color-map-history)',
      note: e.changeCounts.target === null ? `${e.changeCounts.source}번 수정됨` : `각각 ${e.changeCounts.source}회, ${e.changeCounts.target}회 수정됐고 함께 바뀐 커밋 ${e.cochangeCount}개` },
  ]
  return (
    <ul className={styles.metrics}>
      {rows.map((r) => (
        <li key={r.map} className={styles.metric}>
          <div className={styles.metricTop}>
            <span className={styles.swatch} style={{ background: r.color }} aria-hidden="true" />
            <span className={styles.metricMap}>{r.map}</span>
            <span className={`mono num ${styles.metricValue}`}>{r.value}</span>
          </div>
          <div className={styles.metricTrack} aria-hidden="true"><div style={{ background: r.color, transform: `scaleX(${Math.max(0.01, r.ratio)})` }} /></div>
          <p className={styles.metricNote}>{r.note}</p>
        </li>
      ))}
    </ul>
  )
}

export function ComparePage() {
  const { jobId = '', divergenceId = '' } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const job = useQuery({ queryKey: ['job', jobId], queryFn: () => api.getJob(jobId) })
  const list = useQuery({ queryKey: ['divergences', jobId, 'all'], queryFn: () => api.listDivergences(jobId, { limit: 200 }) })
  const detail = useQuery({ queryKey: ['divergence', jobId, divergenceId], queryFn: () => api.getDivergence(jobId, divergenceId) })
  const d = detail.data
  // 메모는 어긋남마다 따로. 다른 항목으로 넘어가면 빈 칸
  const [draft, setDraft] = useState({ id: divergenceId, text: '' })
  const memo = draft.id === divergenceId ? draft.text : ''
  const setMemo = (text: string) => setDraft({ id: divergenceId, text })

  const ids = list.data?.items.map((x) => x.id) ?? []
  const index = ids.indexOf(divergenceId)
  const go = (dir: number) => { const next = ids[index + dir]; if (next) navigate(`/jobs/${jobId}/divergences/${next}`, { replace: true }) }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof Element && e.target.closest('textarea, input, .monaco-editor')) return
      if (e.key === 'ArrowDown') { e.preventDefault(); go(1) }
      if (e.key === 'ArrowUp') { e.preventDefault(); go(-1) }
      if (e.key === 'Escape') navigate(`/jobs/${jobId}/map`)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const verdict = useMutation({
    mutationFn: async (v: Verdict | null) => (v ? api.setVerdict(divergenceId, { verdict: v, memo: memo || undefined }) : api.clearVerdict(divergenceId)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['divergence', jobId, divergenceId] }); qc.invalidateQueries({ queryKey: ['divergences', jobId] }) },
  })
  const current = verdict.isPending ? verdict.variables : d?.verdict ?? null
  const choose = (v: Verdict) => verdict.mutate(current === v ? null : v)

  const type = d ? DIVERGENCE_TYPE[d.type] : null

  return (
    <div className={styles.screen}>
      <TopBar repository={job.data?.repository} commit={job.data?.commit} />
      <div className={styles.header}>
        <Link to={`/jobs/${jobId}/map`} className={styles.back}><ArrowLeftIcon />지도로 돌아가기</Link>
        <span className={styles.divider} aria-hidden="true" />
        {d && type && (
          <>
            <span className="mono">#{String(d.rank).padStart(2, '0')}</span>
            <span className={styles.type} style={{ color: type.color }}>{type.label}</span>
            <span className="mono num">의심도 {d.score}</span>
            <h1 className={styles.headline}>{HEADLINE[d.type]}</h1>
          </>
        )}
        {index >= 0 && <span className={styles.position}>{index + 1} / {ids.length}, ↑ ↓ 키로 이동</span>}
      </div>

      {detail.isError ? (
        <main className={styles.state}>
          <h1 className={styles.stateTitle}>이 어긋남을 불러오지 못했어요</h1>
          <p className={styles.stateText}>목록이 바뀌었거나 연결이 끊겼을 수 있어요.</p>
          <div className={styles.stateActions}>
            <Button variant="primary" onClick={() => detail.refetch()}>다시 불러오기</Button>
            <Button onClick={() => navigate(`/jobs/${jobId}/map`)}>지도로 돌아가기</Button>
          </div>
        </main>
      ) : !d ? (
        <main className={styles.state}><p className={styles.stateText}>코드를 불러오는 중</p></main>
      ) : (
        <main className={styles.body}>
          <div className={styles.codeArea}>
            <div className={styles.panes}>
              <CodePane source={d.sourceCode} highlight={d.similarRanges.map((r) => r.source)} />
              {d.targetCode && <CodePane source={d.targetCode} highlight={d.similarRanges.map((r) => r.target)} />}
            </div>
            {d.similarSummary && (
              <div className={styles.summary}>
                <span className={styles.summarySwatch} aria-hidden="true" />
                <strong>유사 구간 {d.similarRanges.reduce((n, r) => n + r.source[1] - r.source[0] + 1, 0)}줄</strong>
                <span>{d.similarSummary}</span>
              </div>
            )}
          </div>

          <aside className={styles.evidence} aria-labelledby="why-title">
            <div className={styles.evidenceHead}>
              <h2 id="why-title" className={styles.evidenceTitle}>왜 잡혔나요</h2>
              <p className={styles.evidenceSub}>세 지도에서 이 쌍이 놓인 위치</p>
            </div>
            <Metrics d={d} />
            {d.similarNodes.length > 0 && (
              <section className={styles.similar} aria-labelledby="similar-title">
                <h3 id="similar-title" className={styles.sectionLabel}>비슷한 함수 더 보기</h3>
                <ul>
                  {d.similarNodes.map((n) => (
                    <li key={n.nodeId}><span className="mono">{n.nodeId}</span><span className="mono num">{n.similarity.toFixed(2)}</span></li>
                  ))}
                </ul>
              </section>
            )}
            <section className={styles.judgement} aria-labelledby="verdict-title">
              <h3 id="verdict-title" className={styles.sectionLabel}>판단 기록</h3>
              <div className={styles.verdicts}>
                <Button block variant={current === 'real' ? 'primary' : 'secondary'} aria-pressed={current === 'real'} onClick={() => choose('real')}>실제 문제</Button>
                <Button block variant={current === 'false_positive' ? 'primary' : 'secondary'} aria-pressed={current === 'false_positive'} onClick={() => choose('false_positive')}>오탐</Button>
              </div>
              <label className={styles.memo}>
                <span className="sr-only">메모</span>
                <textarea rows={3} value={memo} onChange={(e) => setMemo(e.target.value)}
                  onBlur={() => current && memo && verdict.mutate(current)}
                  placeholder="메모 (선택). 예: 할인 계산을 pricing 모듈로 합치기" />
              </label>
              <p className={styles.evidenceSub} aria-live="polite">
                {verdict.isError ? '저장하지 못했어요. 다시 눌러 주세요.' : current ? '저장했어요. 같은 버튼을 다시 누르면 취소돼요.' : '표시한 판단은 검증 지표와 점수 보정에 쓰입니다.'}
              </p>
            </section>
          </aside>
        </main>
      )}
    </div>
  )
}
