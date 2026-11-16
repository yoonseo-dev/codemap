import type { Divergence } from '../../api'
import { DIVERGENCE_TYPE } from '../../lib/labels'
import styles from './DivergenceItem.module.css'

interface Props {
  d: Divergence
  selected: boolean
  onSelect: () => void
  onOpen: () => void
}

export function DivergenceItem({ d, selected, onSelect, onOpen }: Props) {
  const type = DIVERGENCE_TYPE[d.type]
  return (
    <li>
      <button type="button" className={styles.item} aria-current={selected || undefined} onClick={onSelect} onDoubleClick={onOpen}
        data-divergence-id={d.id}>
        <span className={styles.top}>
          <span className={`mono ${styles.rank}`}>{String(d.rank).padStart(2, '0')}</span>
          <span className={styles.type} style={{ color: type.color }}>{type.label}</span>
          {d.verdict && <span className={styles.verdict}>{d.verdict === 'real' ? '실제 문제' : '오탐'}</span>}
          <span className={`mono num ${styles.score}`}>의심도 {d.score}</span>
        </span>
        <span className={`mono ${styles.source}`}>{d.source}</span>
        <span className={`mono ${styles.summary}`}>{d.summary}</span>
        <span className={styles.track} aria-hidden="true"><span style={{ background: type.color, transform: `scaleX(${d.score / 100})` }} /></span>
      </button>
    </li>
  )
}
