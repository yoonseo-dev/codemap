import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiRequestError } from '../../api'
import { GraphPreview } from '../../components/graph/GraphPreview'
import { Button } from '../../components/ui/Button'
import { AlertIcon } from '../../components/ui/icons'
import { md, num } from '../../lib/labels'
import styles from './LandingPage.module.css'

const LEGEND = [
  { name: '구조', desc: '호출과 import 관계', line: <line x1="0" y1="6" x2="40" y2="6" className={styles.lineStructure} /> },
  { name: '의미', desc: '코드 임베딩 유사도', line: <line x1="0" y1="6" x2="40" y2="6" className={styles.lineSemantic} /> },
  { name: '역사', desc: '함께 수정된 커밋 이력', line: <path d="M0 10 Q20 -4 40 10" className={styles.lineHistory} /> },
]

export function LandingPage() {
  const navigate = useNavigate()
  const [repo, setRepo] = useState('')
  const recent = useQuery({ queryKey: ['recent'], queryFn: api.recentAnalyses })
  // 미리보기는 가장 최근에 분석한 저장소의 지도
  const previewJob = recent.data?.[0]?.jobId
  const preview = useQuery({ queryKey: ['graph', previewJob], queryFn: () => api.getGraph(previewJob!), enabled: !!previewJob })
  const start = useMutation({
    mutationFn: api.createAnalysis,
    onSuccess: (res) => navigate(res.cached ? `/jobs/${res.jobId}/map` : `/jobs/${res.jobId}`),
  })
  const error = start.error instanceof ApiRequestError ? start.error : start.error ? new ApiRequestError(0, 'INTERNAL', '요청을 보내지 못했어요', '잠시 뒤 다시 시도해 주세요') : null

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!repo.trim()) return
    start.mutate(repo.trim())
  }

  return (
    <main className={styles.page}>
      <section className={styles.left}>
        <p className={styles.brand}>Codemap</p>

        <div className={styles.hero}>
          <h1 className={styles.headline}>Where your code’s<br />three maps disagree.</h1>
          <p className={styles.lede}>호출, 의미, 수정 이력을 겹쳐 서로 어긋나는 코드를 찾습니다.</p>

          <form className={styles.form} onSubmit={submit} noValidate>
            <div className={styles.row}>
              <label className={`${styles.input} ${error ? styles.inputError : ''}`}>
                <span className={styles.prefix}>github.com/</span>
                <input value={repo} onChange={(e) => { setRepo(e.target.value); start.reset() }}
                  placeholder="owner/repository" aria-label="GitHub 저장소" aria-invalid={!!error}
                  aria-describedby="repo-help" autoComplete="off" spellCheck={false} />
              </label>
              <Button variant="primary" size="page" type="submit" disabled={start.isPending}>
                {start.isPending ? '확인 중' : '분석 시작'}
              </Button>
            </div>
            <div id="repo-help" className={styles.help} aria-live="polite">
              {error ? (
                <div className={styles.error}>
                  <AlertIcon className={styles.errorIcon} />
                  <div>
                    <p className={styles.errorTitle}>{error.message}</p>
                    {error.hint && <p className={styles.errorHint}>{error.hint}</p>}
                  </div>
                </div>
              ) : (
                <p>Java와 Python 저장소를 분석해요</p>
              )}
            </div>
          </form>
        </div>

        <section className={styles.recent} aria-labelledby="recent-title">
          <h2 id="recent-title" className={styles.recentTitle}>최근 분석한 저장소</h2>
          {recent.isPending && <p className={styles.muted}>불러오는 중</p>}
          {recent.data?.length === 0 && <p className={styles.muted}>아직 분석한 저장소가 없어요. 위에 주소를 넣어 시작해 보세요.</p>}
          <ul className={styles.recentList}>
            {recent.data?.map((r) => (
              <li key={r.jobId}>
                <Link to={`/jobs/${r.jobId}/map`} className={styles.recentRow}>
                  <span className={`mono ${styles.recentRepo}`}>{r.repository.owner}/{r.repository.name}</span>
                  <span className={styles.recentMeta}>함수 {num(r.functionCount)}개</span>
                  <span className={styles.recentDiv}>어긋남 {r.divergenceCount}개</span>
                  <span className={`mono ${styles.recentDate}`}>{md(r.finishedAt)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </section>

      <section className={styles.right} aria-label="결과 지도 미리보기">
        {recent.data?.[0] && (
          <p className={styles.caption}>
            <span className="mono">{recent.data[0].repository.owner}/{recent.data[0].repository.name}</span>를 하는 일별 보기로 그린 지도
          </p>
        )}
        <div className={styles.preview}>
          {preview.data && <GraphPreview graph={preview.data} width={620} height={560} label="예시 저장소의 함수 연결 지도" />}
        </div>
        <div className={styles.legend}>
          <h2 className={styles.recentTitle}>세 가지 지도</h2>
          {LEGEND.map((l) => (
            <div key={l.name} className={styles.legendRow}>
              <svg width="40" height="12" viewBox="0 0 40 12" aria-hidden="true">{l.line}</svg>
              <span className={styles.legendName}>{l.name}</span>
              <span className={styles.legendDesc}>{l.desc}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}
