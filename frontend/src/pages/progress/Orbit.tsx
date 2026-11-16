import type { Stage } from '../../api'
import { STAGE_LABEL } from '../../lib/labels'
import styles from './Orbit.module.css'

const SIZE = 680
const C = SIZE / 2
const RADII = [110, 160, 210, 260, 310]

function arc(r: number, p: number) {
  const a = -Math.PI / 2 + p * 2 * Math.PI
  return `M${C} ${C - r} A${r} ${r} 0 ${p > 0.5 ? 1 : 0} 1 ${C + r * Math.cos(a)} ${C + r * Math.sin(a)}`
}

/** 5단계를 안쪽부터 동심원으로 그린 진행 표시 */
export function Orbit({ stages }: { stages: Stage[] }) {
  const active = stages.find((s) => s.status === 'RUNNING' || s.status === 'FAILED') ?? stages.findLast((s) => s.status === 'DONE')
  const overall = active?.status === 'DONE' ? 100 : Math.floor(active?.percent ?? 0)
  return (
    <svg className={styles.svg} viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden="true">
      {stages.map((s, i) => {
        const r = RADII[i]
        const p = s.percent / 100
        const end = { x: C + r * Math.cos(-Math.PI / 2 + p * 2 * Math.PI), y: C + r * Math.sin(-Math.PI / 2 + p * 2 * Math.PI) }
        const tone = s.status === 'FAILED' ? styles.failed : styles.running
        return (
          <g key={s.stage}>
            <circle className={styles.base} cx={C} cy={C} r={r} />
            {s.status === 'DONE' && <circle className={styles.done} cx={C} cy={C} r={r} />}
            {(s.status === 'RUNNING' || s.status === 'FAILED') && p > 0 && (
              <>
                <path className={`${styles.arc} ${tone}`} d={arc(r, Math.min(p, 0.9999))} />
                <circle className={`${styles.head} ${tone}`} cx={end.x} cy={end.y} r={5} />
              </>
            )}
            <text className={`${styles.label} ${s.status === 'RUNNING' ? styles.labelActive : s.status === 'FAILED' ? styles.labelFailed : ''}`} x={C + 10} y={C - r - 8}>
              {STAGE_LABEL[s.stage].replace(' 지도', '').replace('어긋남 ', '')}
            </text>
          </g>
        )
      })}
      <text className={styles.percent} x={C} y={C + 18} textAnchor="middle">{overall}%</text>
      {active && <text className={`${styles.caption} ${active.status === 'FAILED' ? styles.labelFailed : ''}`} x={C} y={C + 48} textAnchor="middle">
        {active.status === 'FAILED' ? `${STAGE_LABEL[active.stage]} 단계에서 멈춤` : STAGE_LABEL[active.stage]}
      </text>}
    </svg>
  )
}
