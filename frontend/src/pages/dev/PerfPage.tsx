// 개발 모드 전용: 큰 그래프로 3D 지도 성능을 잰다. /dev/perf?n=5000&e=20000
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { EdgeKind, Graph, LayoutMode } from '../../api'
import { rng } from '../../api/mock/fixtures'
import { MapScene } from '../../components/graph3d/MapScene'
import { useLayouts } from '../../components/graph3d/useLayouts'

function syntheticGraph(n: number, e: number): Graph {
  const r = rng(42)
  const moduleCount = Math.max(4, Math.round(n / 250))
  const modules = Array.from({ length: moduleCount }, (_, i) => ({ id: `m${i}/`, label: `m${i}`, hubNodeId: `m${i}/a.py::f0` }))
  const centers = modules.map(() => [r() * 20 - 10, r() * 20 - 10, r() * 20 - 10])
  const nodes = Array.from({ length: n }, (_, i) => {
    const m = i % moduleCount, c = centers[m]
    return { id: i < moduleCount ? `m${m}/a.py::f0` : `m${m}/a.py::f${i}`, name: `f${i}`, path: `m${m}/a.py`, moduleId: `m${m}/`, kind: 'function' as const, lines: [1, 10] as [number, number], degree: 1 + Math.floor(r() * 12), semanticPosition: [c[0] + r() * 4, c[1] + r() * 4, c[2] + r() * 4] as [number, number, number] }
  })
  const kinds: EdgeKind[] = ['call', 'call', 'call', 'similar', 'cochange']
  const edges = Array.from({ length: e }, () => {
    const a = Math.floor(r() * n)
    const sameModule = r() < 0.85
    const b = sameModule ? (a + moduleCount * (1 + Math.floor(r() * 20))) % n : Math.floor(r() * n)
    return { source: nodes[a].id, target: nodes[b].id, kind: kinds[Math.floor(r() * kinds.length)], weight: 1 }
  })
  return { jobId: 'perf', stats: { functions: n, files: moduleCount, commits: 0 }, modules, nodes, edges }
}

export function PerfPage() {
  const [params] = useSearchParams()
  const n = Number(params.get('n') ?? 5000), e = Number(params.get('e') ?? 20000)
  const mode = (params.get('mode') ?? 'semantic') as LayoutMode
  const graph = useMemo(() => syntheticGraph(n, e), [n, e])
  const started = useRef(0)
  const layouts = useLayouts(graph)
  const [result, setResult] = useState<{ fps: number; layoutMs: number | null } | null>(null)
  const layoutMs = useRef<number | null>(null)
  useEffect(() => { started.current = performance.now() }, [graph])
  useEffect(() => {
    if (!layouts?.structure || layoutMs.current !== null) return
    layoutMs.current = Math.round(performance.now() - started.current)
    ;(window as unknown as { __layoutMs: number }).__layoutMs = layoutMs.current
  }, [layouts])

  useEffect(() => {
    if (!layouts) return
    let frames = 0, raf = 0
    const t0 = performance.now()
    const tick = () => { frames++; if (performance.now() - t0 < 5000) raf = requestAnimationFrame(tick); else { const r = { fps: Math.round(frames / 5), layoutMs: layoutMs.current }; setResult(r); (window as unknown as { __perf: unknown }).__perf = r } }
    const wait = setTimeout(() => { raf = requestAnimationFrame(tick) }, 1500)
    return () => { clearTimeout(wait); cancelAnimationFrame(raf) }
  }, [layouts])

  return (
    <div style={{ position: 'relative', height: '100dvh' }}>
      {layouts && (
        <MapScene graph={graph} layouts={layouts} mode={mode} layers={{ structure: true, semantic: true, history: true }}
          focus={null} hovered={null} onHover={() => {}} onSelectNode={() => {}} onBackground={() => {}} command={null} label="성능 측정용 그래프" />
      )}
      <p className="mono" style={{ position: 'absolute', top: 16, left: 16 }}>
        점 {n}개, 선 {e}개 · {result ? `${result.fps} fps, 폴더별 배치 계산 ${result.layoutMs ?? '진행 중'}ms` : '측정 중 (5초)'}
      </p>
    </div>
  )
}
