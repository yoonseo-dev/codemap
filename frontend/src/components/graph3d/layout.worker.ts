// 폴더별 보기 좌표 계산. 두 단계로 나눈다.
//   1) 폴더 안: 대표 함수를 가운데 두고, 호출을 따라 한 단계 떨어질 때마다 한 겹 바깥 껍질에 둔다.
//      불린 함수는 부른 함수 쪽 방향에 모여서, 호출 흐름이 가지처럼 보인다. 계산은 함수 수에 비례(즉시).
//   2) 폴더끼리: 폴더 사이 호출이 많을수록 가깝게 force 레이아웃 (폴더 수만큼이라 가볍다)
import { forceLink, forceManyBody, forceSimulation, type SimNode } from 'd3-force-3d'

export interface LayoutRequest {
  nodes: { id: string; moduleId: string }[]
  links: { source: string; target: string }[]
  /** 폴더 대표 함수 (폴더 id → 함수 id). 없으면 연결이 가장 많은 함수 */
  hubs: Record<string, string>
  /** 결과를 이 반지름 안으로 맞춘다 */
  radius: number
}

const STEP = 1.6

/** 피보나치 구: 고르게 퍼진 방향 n개 */
function directions(n: number): [number, number, number][] {
  return Array.from({ length: n }, (_, i) => {
    const y = n === 1 ? 0 : 1 - (2 * (i + 0.5)) / n
    const r = Math.sqrt(1 - y * y), t = i * Math.PI * (3 - Math.sqrt(5))
    return [Math.cos(t) * r, y, Math.sin(t) * r]
  })
}

function radialTree(ids: string[], adj: Map<string, string[]>, hub: string) {
  const pos = new Map<string, [number, number, number]>()
  const dir = new Map<string, [number, number, number]>()
  const depth = new Map<string, number>([[hub, 0]])
  pos.set(hub, [0, 0, 0])
  // 너비 우선으로 단계를 매긴다. 대표 함수에서 닿지 않는 함수는 1단계에 둔다
  const order = [hub]
  const parent = new Map<string, string>()
  for (let q = 0; q < order.length; q++) for (const nb of adj.get(order[q]) ?? []) if (!depth.has(nb)) { depth.set(nb, depth.get(order[q])! + 1); parent.set(nb, order[q]); order.push(nb) }
  for (const id of ids) if (!depth.has(id)) { depth.set(id, 1); parent.set(id, hub); order.push(id) }

  const firstRing = order.filter((id) => depth.get(id) === 1)
  directions(firstRing.length).forEach((d, i) => dir.set(firstRing[i], d))
  let radius = STEP
  for (const id of order) {
    if (id === hub) continue
    const d = depth.get(id)!
    let v = dir.get(id)
    if (!v) {
      const p = dir.get(parent.get(id)!) ?? [0, 1, 0]
      const spread = 0.55 / d
      v = [p[0] + (Math.random() - 0.5) * spread, p[1] + (Math.random() - 0.5) * spread, p[2] + (Math.random() - 0.5) * spread]
      const len = Math.hypot(...v)
      v = [v[0] / len, v[1] / len, v[2] / len]
      dir.set(id, v)
    }
    const r = d * STEP * (0.9 + Math.random() * 0.2)
    radius = Math.max(radius, r)
    pos.set(id, [v[0] * r, v[1] * r, v[2] * r])
  }
  return { pos, radius }
}

self.onmessage = (e: MessageEvent<LayoutRequest>) => {
  const { nodes, links, hubs, radius } = e.data
  const moduleOf = new Map(nodes.map((n) => [n.id, n.moduleId]))
  const byModule = new Map<string, string[]>()
  for (const n of nodes) byModule.set(n.moduleId, [...(byModule.get(n.moduleId) ?? []), n.id])
  const adj = new Map<string, string[]>()
  const degree = new Map<string, number>()
  const between = new Map<string, number>()
  for (const l of links) {
    const a = moduleOf.get(l.source), b = moduleOf.get(l.target)
    if (!a || !b || l.source === l.target) continue
    degree.set(l.source, (degree.get(l.source) ?? 0) + 1)
    degree.set(l.target, (degree.get(l.target) ?? 0) + 1)
    if (a === b) {
      adj.set(l.source, [...(adj.get(l.source) ?? []), l.target])
      adj.set(l.target, [...(adj.get(l.target) ?? []), l.source])
    } else {
      const k = a < b ? `${a}\n${b}` : `${b}\n${a}`
      between.set(k, (between.get(k) ?? 0) + 1)
    }
  }

  // 1) 폴더 안
  const local = new Map<string, Map<string, [number, number, number]>>()
  const moduleRadius = new Map<string, number>()
  for (const [m, ids] of byModule) {
    const hub = hubs[m] && ids.includes(hubs[m]) ? hubs[m] : ids.reduce((best, id) => ((degree.get(id) ?? 0) > (degree.get(best) ?? 0) ? id : best), ids[0])
    const { pos, radius: r } = radialTree(ids, adj, hub)
    local.set(m, pos)
    moduleRadius.set(m, r)
  }

  // 2) 폴더끼리
  const modules = [...byModule.keys()].map((id): SimNode => ({ id, x: Math.random() * 10, y: Math.random() * 10, z: Math.random() * 10 }))
  const moduleLinks = [...between].map(([k]) => { const [source, target] = k.split('\n'); return { source, target } })
  const r = (id: string) => moduleRadius.get(id) ?? STEP
  forceSimulation(modules, 3)
    .force('link', forceLink(moduleLinks).id((n) => n.id as string).distance((l) => r(l.source.id as string) + r(l.target.id as string) + STEP * 2).strength(0.3))
    .force('charge', forceManyBody().strength((n) => -Math.pow(r(n.id as string), 2) * 4))
    .stop()
    .tick(200)

  // 합치고 원점 중심, 반지름에 맞춤
  const index = new Map(nodes.map((n, i) => [n.id, i]))
  const out = new Float32Array(nodes.length * 3)
  let cx = 0, cy = 0, cz = 0
  for (const m of modules) { cx += m.x!; cy += m.y!; cz += m.z! }
  cx /= modules.length; cy /= modules.length; cz /= modules.length
  let max = 0
  for (const m of modules) {
    for (const [id, p] of local.get(m.id as string)!) {
      const i = index.get(id)!
      out[i * 3] = m.x! - cx + p[0]; out[i * 3 + 1] = m.y! - cy + p[1]; out[i * 3 + 2] = m.z! - cz + p[2]
      max = Math.max(max, Math.hypot(out[i * 3], out[i * 3 + 1], out[i * 3 + 2]))
    }
  }
  const s = max ? radius / max : 1
  for (let i = 0; i < out.length; i++) out[i] *= s
  ;(self as unknown as Worker).postMessage(out, [out.buffer])
}
