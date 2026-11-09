import { useMemo } from 'react'
import type { Graph, NodeId } from '../../api'
import styles from './GraphPreview.module.css'

interface Props {
  graph: Graph
  width: number
  height: number
  /** 강조할 어긋남 쌍 */
  focus?: [NodeId, NodeId | null] | null
  label: string
}

const YAW = 0.6
const PITCH = 0.3

/** 하는 일별 좌표(semanticPosition)를 원근 투영한 2D 그림. 3D 지도가 들어오기 전까지 쓰는 미리보기 */
export function GraphPreview({ graph, width, height, focus, label }: Props) {
  const layout = useMemo(() => {
    const cy = Math.cos(YAW), sy = Math.sin(YAW), cp = Math.cos(PITCH), sp = Math.sin(PITCH)
    const pts = graph.nodes.map((n) => {
      const [x, y, z] = n.semanticPosition
      const x1 = x * cy + z * sy, z1 = -x * sy + z * cy
      const y1 = y * cp - z1 * sp, z2 = y * sp + z1 * cp
      return { id: n.id, x: x1, y: y1, z: z2 }
    })
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y), zs = pts.map((p) => p.z)
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
    const [minZ, maxZ] = [Math.min(...zs), Math.max(...zs)]
    const pad = 32
    const s = Math.min((width - pad * 2) / (maxX - minX), (height - pad * 2) / (maxY - minY))
    const ox = (width - (maxX - minX) * s) / 2, oy = (height - (maxY - minY) * s) / 2
    const pos = new Map(pts.map((p) => [p.id, { x: ox + (p.x - minX) * s, y: oy + (p.y - minY) * s, depth: 1 - (p.z - minZ) / (maxZ - minZ || 1) }]))
    return pos
  }, [graph, width, height])

  const hubs = new Set(graph.modules.map((m) => m.hubNodeId))
  const focusIds = new Set(focus?.filter(Boolean) as NodeId[] | undefined)
  const curve = (a: { x: number; y: number }, b: { x: number; y: number }, bend: number) => {
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, dx = b.x - a.x, dy = b.y - a.y
    return `M${a.x} ${a.y} Q${mx - dy * bend} ${my + dx * bend} ${b.x} ${b.y}`
  }

  return (
    <svg className={styles.svg} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      {graph.edges.map((e, i) => {
        const a = layout.get(e.source), b = layout.get(e.target)
        if (!a || !b) return null
        if (e.kind === 'call' || e.kind === 'import')
          return <line key={i} className={styles.structure} x1={a.x} y1={a.y} x2={b.x} y2={b.y} style={{ opacity: 0.12 + 0.35 * ((a.depth + b.depth) / 2) }} />
        return <path key={i} className={e.kind === 'similar' ? styles.semantic : styles.history} d={curve(a, b, e.kind === 'similar' ? -0.12 : 0.22)} />
      })}
      {graph.nodes.map((n) => {
        const p = layout.get(n.id)!
        const r = 1.6 + Math.sqrt(n.degree) * 1.2
        if (hubs.has(n.id))
          return <g key={n.id}><circle className={styles.hubRing} cx={p.x} cy={p.y} r={r + 3} /><circle className={styles.node} cx={p.x} cy={p.y} r={r * 0.45} /></g>
        return <circle key={n.id} className={styles.node} cx={p.x} cy={p.y} r={r} style={{ opacity: 0.3 + 0.7 * p.depth }} />
      })}
      {[...focusIds].map((id) => {
        const p = layout.get(id)
        return p && <circle key={id} className={styles.focusRing} cx={p.x} cy={p.y} r={14} />
      })}
    </svg>
  )
}
