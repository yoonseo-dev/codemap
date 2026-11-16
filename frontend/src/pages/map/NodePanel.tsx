import { useQuery } from '@tanstack/react-query'
import { api, type NodeId } from '../../api'
import { DivergenceItem } from '../../components/divergence/DivergenceItem'
import { ArrowLeftIcon } from '../../components/ui/icons'
import { ymd } from '../../lib/labels'
import styles from './MapPage.module.css'

const RELATION = { calls: '호출함', called_by: '호출됨', cochange: '같이 수정', similar: '하는 일 비슷' } as const
const RELATION_COLOR = { calls: 'var(--color-map-structure)', called_by: 'var(--color-map-structure)', cochange: 'var(--color-map-history)', similar: 'var(--color-map-semantic)' } as const

interface Props {
  jobId: string
  nodeId: NodeId
  onBack: () => void
  onSelectNode: (id: NodeId) => void
  onSelectDivergence: (id: string) => void
  onOpenDivergence: (id: string) => void
}

/** 지도에서 함수 하나를 골랐을 때 오른쪽 패널 */
export function NodePanel({ jobId, nodeId, onBack, onSelectNode, onSelectDivergence, onOpenDivergence }: Props) {
  const q = useQuery({ queryKey: ['node', jobId, nodeId], queryFn: () => api.getNode(jobId, nodeId) })
  const d = q.data
  const stats = d && [
    { n: d.counts.calls, label: '호출함', color: 'var(--color-map-structure)' },
    { n: d.counts.calledBy, label: '호출됨', color: 'var(--color-map-structure)' },
    { n: d.counts.similar, label: '하는 일 비슷', color: 'var(--color-map-semantic)' },
    { n: d.counts.cochanged, label: '같이 수정', color: 'var(--color-map-history)' },
  ]
  return (
    <>
      <div className={styles.panelHead}>
        <button type="button" className={styles.back} onClick={onBack}><ArrowLeftIcon size={14} />어긋남 목록으로</button>
        <h2 className={styles.title}>함수 정보</h2>
        <p className="mono">{nodeId}</p>
        {d && <p className={styles.muted}>{d.node.moduleId} 폴더, {d.node.lines[0]}~{d.node.lines[1]}행, 마지막 수정 {ymd(d.lastModified)}</p>}
      </div>
      <div className={styles.listWrap}>
        {q.isPending && <p className={`${styles.muted} ${styles.pad}`}>불러오는 중</p>}
        {q.isError && <p className={`${styles.muted} ${styles.pad}`}>함수 정보를 불러오지 못했어요</p>}
        {stats && (
          <dl className={styles.statGrid}>
            {stats.map((s) => (
              <div key={s.label} className={styles.stat}>
                <dt className={styles.statLabel}><span className={styles.swatch} style={{ background: s.color }} aria-hidden="true" />{s.label}</dt>
                <dd className="num">{s.n}</dd>
              </div>
            ))}
          </dl>
        )}
        {d && d.divergences.length > 0 && (
          <section>
            <h3 className={`${styles.sectionLabel} ${styles.pad}`}>이 함수가 낀 어긋남 {d.divergences.length}개</h3>
            <ul className={styles.list}>
              {d.divergences.map((x) => <DivergenceItem key={x.id} d={x} selected={false} onSelect={() => onSelectDivergence(x.id)} onOpen={() => onOpenDivergence(x.id)} />)}
            </ul>
          </section>
        )}
        {d && d.linked.length > 0 && (
          <section className={styles.pad}>
            <h3 className={styles.sectionLabel}>연결된 함수</h3>
            <ul className={styles.linked}>
              {d.linked.map((l) => (
                <li key={`${l.relation}-${l.nodeId}`}>
                  <button type="button" onClick={() => onSelectNode(l.nodeId)}>
                    <span className={styles.swatch} style={{ background: RELATION_COLOR[l.relation] }} aria-hidden="true" />
                    <span className="mono">{l.nodeId}</span>
                    <span className={styles.muted}>{RELATION[l.relation]}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </>
  )
}
