import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type Job, type Stage } from '../../api'
import { TopBar } from '../../components/layout/TopBar'
import { Button } from '../../components/ui/Button'
import { AlertIcon } from '../../components/ui/icons'
import { STAGE_LABEL } from '../../lib/labels'
import { Orbit } from './Orbit'
import styles from './ProgressPage.module.css'

const hhmm = (iso: string) => new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false })
const duration = (ms: number) => { const s = Math.max(0, Math.round(ms / 1000)); return s >= 60 ? `${Math.floor(s / 60)}분 ${s % 60}초` : `${s}초` }

function statusText(s: Stage) {
  switch (s.status) {
    case 'DONE': return '완료'
    case 'RUNNING': return `${Math.floor(s.percent)}%`
    case 'FAILED': return '실패'
    case 'CANCELLED': return '중단됨'
    default: return '대기'
  }
}

export function ProgressPage() {
  const { jobId = '' } = useParams()
  const navigate = useNavigate()
  const initial = useQuery({ queryKey: ['job', jobId], queryFn: () => api.getJob(jobId), staleTime: 0 })
  const [job, setJob] = useState<Job | null>(null)
  const [notify, setNotify] = useState<NotificationPermission>(typeof Notification === 'undefined' ? 'denied' : Notification.permission)
  // 이벤트로 바뀐 상태가 있으면 그것, 없으면 처음 받은 상태
  const current = job ?? initial.data ?? null
  const status = current?.status
  const repoLabel = current ? `${current.repository.owner}/${current.repository.name}` : ''

  // 진행 이벤트 구독
  useEffect(() => {
    if (!status || status === 'DONE' || status === 'FAILED') return
    return api.subscribeJob(jobId, (e) => {
      setJob((state) => {
        const prev = state ?? initial.data
        if (!prev) return state
        if (e.type === 'stage') return { ...prev, status: 'RUNNING', stage: e.stage.stage, stages: prev.stages.map((s) => (s.stage === e.stage.stage ? e.stage : s)) }
        if (e.type === 'done') return { ...prev, status: 'DONE', finishedAt: new Date().toISOString() }
        return {
          ...prev, status: 'FAILED', failure: e.failure, finishedAt: new Date().toISOString(),
          stages: prev.stages.map((s) => (s.status === 'PENDING' ? { ...s, status: 'CANCELLED' } : s)),
        }
      })
    })
  }, [jobId, status, initial.data])

  // 끝나면 알림을 보내고 지도로 이동
  useEffect(() => {
    if (status !== 'DONE') return
    if (notify === 'granted' && document.hidden) new Notification('분석이 끝났어요', { body: `${repoLabel} 지도를 열 수 있어요` })
    const t = setTimeout(() => navigate(`/jobs/${jobId}/map`, { replace: true }), 900)
    return () => clearTimeout(t)
  }, [status, notify, repoLabel, navigate, jobId])

  // 경과 시간 표시용 현재 시각
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [])

  const retry = useMutation({ mutationFn: () => api.retryJob(jobId), onSuccess: setJob })

  if (initial.isError) {
    return (
      <div className={styles.screen}>
        <TopBar />
        <main className={styles.missing}>
          <h1 className={styles.title}>분석 작업을 찾지 못했어요</h1>
          <p className={styles.meta}>주소가 틀렸거나 오래된 작업일 수 있어요.</p>
          <Button variant="primary" onClick={() => navigate('/')}>저장소 다시 입력하기</Button>
        </main>
      </div>
    )
  }
  if (!current) return <div className={styles.screen}><TopBar /></div>

  const failed = current.status === 'FAILED'
  const failedIndex = current.stages.findIndex((s) => s.status === 'FAILED')
  const repoName = repoLabel
  const started = current.startedAt
  const title = failed ? `분석이 ${failedIndex + 1}단계에서 멈췄어요`
    : current.status === 'DONE' ? `${repoName} 분석이 끝났어요`
    : current.status === 'QUEUED' ? `${repoName} 분석 대기 중` : `${repoName} 분석 중`
  const meta = !started ? '곧 시작해요'
    : failed ? `${repoName}, ${hhmm(started)}에 시작해 ${duration(Date.parse(current.finishedAt ?? '') - Date.parse(started))} 만에 멈춤`
    : `${hhmm(started)}에 시작했고 ${duration(now - Date.parse(started))} 지났어요`

  return (
    <div className={styles.screen}>
      <TopBar repository={current.repository} commit={current.commit} />
      <main className={styles.body}>
        <section className={styles.left}>
          <div className={styles.head}>
            <h1 className={styles.title} aria-live="polite">{title}</h1>
            <p className={styles.meta}>{meta}</p>
          </div>

          <ol className={styles.stages}>
            {current.stages.map((s, i) => (
              <li key={s.stage} className={`${styles.stage} ${styles[s.status.toLowerCase()]}`}>
                <div className={styles.stageRow}>
                  <span className={`mono ${styles.index}`}>{String(i + 1).padStart(2, '0')}</span>
                  <div className={styles.stageText}>
                    <p className={styles.stageName}>{STAGE_LABEL[s.stage]}</p>
                    <p className={styles.stageDetail}>{s.detail ?? ' '}</p>
                  </div>
                  <span className={`mono num ${styles.status}`}>{statusText(s)}</span>
                </div>
                <div className={styles.track} aria-hidden="true"><div className={styles.bar} style={{ transform: `scaleX(${s.percent / 100})` }} /></div>
              </li>
            ))}
          </ol>

          {failed && current.failure ? (
            <div className={`${styles.note} ${styles.noteError}`} role="alert">
              <p className={styles.noteHead}><AlertIcon className={styles.errorIcon} />앞 단계 결과는 저장돼 있어요</p>
              <p className={styles.noteBody}>
                {failedIndex > 0 && `앞의 ${failedIndex}단계(${current.stages.slice(0, failedIndex).map((s) => STAGE_LABEL[s.stage]).join(', ')})는 끝났습니다. `}
                {current.failure.resumable ? `다시 시도하면 처음부터가 아니라 ${failedIndex + 1}단계(${STAGE_LABEL[current.failure.stage]})부터 이어서 진행해요.` : '이 작업은 처음부터 다시 분석해야 해요.'}
              </p>
              <div className={styles.noteActions}>
                {current.failure.resumable && (
                  <Button variant="primary" onClick={() => retry.mutate()} disabled={retry.isPending}>{failedIndex + 1}단계부터 다시 시도</Button>
                )}
                <Button onClick={() => navigate('/')}>다른 저장소 분석</Button>
              </div>
            </div>
          ) : current.status !== 'DONE' && (
            <div className={styles.note}>
              <p className={styles.noteBody}>분석이 끝나면 알림을 보내드려요. 창을 닫아도 분석은 계속됩니다.</p>
              <Button disabled={notify !== 'default'} onClick={async () => setNotify(await Notification.requestPermission())}>
                {notify === 'granted' ? '알림을 켰어요' : notify === 'denied' ? '알림이 꺼져 있어요' : '완료 알림 받기'}
              </Button>
            </div>
          )}
        </section>
        <section className={styles.right} aria-hidden="true">
          <Orbit stages={current.stages} />
        </section>
      </main>
    </div>
  )
}
