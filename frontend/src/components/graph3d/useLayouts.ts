import { useEffect, useMemo, useState } from 'react'
import type { Graph } from '../../api'
import type { LayoutRequest } from './layout.worker'

export const RADIUS = 12

/** 노드 순서(graph.nodes)대로 xyz가 이어진 좌표 배열 두 벌 */
export interface Layouts {
  structure: Float32Array | null
  semantic: Float32Array
}

function fitSemantic(graph: Graph): Float32Array {
  const n = graph.nodes.length
  const out = new Float32Array(n * 3)
  let cx = 0, cy = 0, cz = 0
  for (const node of graph.nodes) { cx += node.semanticPosition[0]; cy += node.semanticPosition[1]; cz += node.semanticPosition[2] }
  cx /= n; cy /= n; cz /= n
  let max = 0
  for (const { semanticPosition: p } of graph.nodes) max = Math.max(max, Math.hypot(p[0] - cx, p[1] - cy, p[2] - cz))
  const s = max ? RADIUS / max : 1
  graph.nodes.forEach(({ semanticPosition: p }, i) => { out[i * 3] = (p[0] - cx) * s; out[i * 3 + 1] = (p[1] - cy) * s; out[i * 3 + 2] = (p[2] - cz) * s })
  return out
}

export function useLayouts(graph: Graph | undefined): Layouts | null {
  const semantic = useMemo(() => (graph ? fitSemantic(graph) : null), [graph])
  const [structure, setStructure] = useState<{ graph: Graph; pos: Float32Array } | null>(null)

  useEffect(() => {
    if (!graph) return
    const worker = new Worker(new URL('./layout.worker.ts', import.meta.url), { type: 'module' })
    worker.onmessage = (e: MessageEvent<Float32Array>) => { setStructure({ graph, pos: e.data }); worker.terminate() }
    const req: LayoutRequest = {
      nodes: graph.nodes.map((n) => ({ id: n.id, moduleId: n.moduleId })),
      links: graph.edges.filter((e) => e.kind === 'call' || e.kind === 'import').map((e) => ({ source: e.source, target: e.target })),
      hubs: Object.fromEntries(graph.modules.map((m) => [m.id, m.hubNodeId])),
      radius: RADIUS,
    }
    worker.postMessage(req)
    return () => worker.terminate()
  }, [graph])

  if (!graph || !semantic) return null
  return { semantic, structure: structure?.graph === graph ? structure.pos : null }
}
