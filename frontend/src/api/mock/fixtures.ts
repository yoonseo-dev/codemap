// 가짜 데이터. 화면 개발용 견본이며 실제 저장소를 분석한 값이 아니다.
import type {
  Divergence,

  Graph,
  GraphEdge,
  GraphNode,
  Module,
  NodeId,
  SourceCode,
  Timeline,
  Vec3,
} from '../types'

export function rng(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function hash(s: string) {
  let h = 2166136261
  for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  return h >>> 0
}

interface ModuleSpec {
  id: string
  center: Vec3
  /** 이름을 정해 둔 함수 (어긋남 견본에 쓰임). 첫 번째가 폴더 대표 함수 */
  named: string[]
  files: string[]
}

const MODULES: ModuleSpec[] = [
  { id: 'billing/', center: [-2.5, -0.4, 0.6], files: ['invoice.py', 'tax.py', 'refund.py', 'report.py'],
    named: ['billing/invoice.py::InvoiceService.create', 'billing/invoice.py::calc_total', 'billing/tax.py::rate_for', 'billing/report.py::to_rows', 'billing/invoice.py::send_receipt', 'billing/refund.py::refund_amount'] },
  { id: 'orders/', center: [2.4, 0.5, -0.4], files: ['service.py', 'cart.py', 'controller.py'],
    named: ['orders/controller.py::OrderController.place', 'orders/cart.py::sum_items', 'orders/service.py::place_order', 'orders/service.py::send_order_mail', 'orders/service.py::OrderService.reserve_stock'] },
  { id: 'auth/', center: [-0.4, -2.1, -1.7], files: ['session.py', 'signup.py', 'profile.py'],
    named: ['auth/session.py::SessionStore.get', 'auth/session.py::refresh', 'auth/signup.py::validate_email', 'auth/profile.py::normalize_phone', 'auth/session.py::require_login'] },
  { id: 'api/', center: [0.1, 0.2, 1.3], files: ['router.py', 'validators.py', 'routes.py', 'export.py'],
    named: ['api/router.py::dispatch', 'api/validators.py::check_email', 'api/routes.py::export_csv', 'api/export.py::sum_rows'] },
  { id: 'notify/', center: [-2.1, 1.8, -0.6], files: ['mailer.py', 'sms.py', 'sender.py'],
    named: ['notify/mailer.py::Mailer.deliver', 'notify/mailer.py::render_template', 'notify/sms.py::format_phone', 'notify/mailer.py::send', 'notify/sms.py::send_sms', 'notify/mailer.py::send_bulk'] },
  { id: 'catalog/', center: [2.5, -2.0, 0.8], files: ['price.py', 'product.py'],
    named: ['catalog/price.py::PriceRule.apply', 'catalog/price.py::apply_discount', 'catalog/price.py::line_total'] },
]

const FILLER = ['load', 'save', 'parse', 'build', 'to_dict', 'from_row', 'validate', 'normalize', 'format', 'fetch', 'update', 'remove', 'merge', 'split', 'lookup', 'resolve']

const nameOf = (id: NodeId) => id.split('::')[1]
const pathOf = (id: NodeId) => id.split('::')[0]

export function buildGraph(jobId: string, scale = 1): Graph {
  const r = rng(hash(jobId))
  const g = () => { let u = 0, v = 0; while (!u) u = r(); while (!v) v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v) }
  const nodes: GraphNode[] = []
  const modules: Module[] = []
  for (const m of MODULES) {
    const ids = [...m.named]
    const extra = Math.round((10 + r() * 8) * scale)
    for (let i = 0; i < extra; i++) ids.push(`${m.id}${m.files[i % m.files.length]}::${FILLER[(i * 7 + m.id.length) % FILLER.length]}_${i}`)
    modules.push({ id: m.id, label: m.id.replace('/', ''), hubNodeId: ids[0] })
    ids.forEach((id, i) => {
      const start = 10 + Math.floor(r() * 200)
      const spread = i === 0 ? 0.15 : 0.7
      nodes.push({
        id, name: nameOf(id), path: pathOf(id), moduleId: m.id,
        kind: nameOf(id).includes('.') ? 'method' : 'function',
        lines: [start, start + 6 + Math.floor(r() * 40)],
        degree: 0,
        semanticPosition: [m.center[0] + g() * spread, m.center[1] + g() * spread, m.center[2] + g() * spread],
      })
    })
  }
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const edges: GraphEdge[] = []
  const pick = <T,>(list: T[]) => list[Math.floor(r() * list.length)]
  const call = (a: NodeId, b: NodeId) => { if (a === b || !byId.has(a) || !byId.has(b)) return; edges.push({ source: a, target: b, kind: 'call', weight: 1 + Math.floor(r() * 3) }); byId.get(a)!.degree++; byId.get(b)!.degree++ }
  const since = () => new Date(Date.UTC(2024, 2 + Math.floor(r() * 30), 1 + Math.floor(r() * 27))).toISOString()

  // 구조: 실제 코드처럼 호출은 대부분 같은 폴더 안, 같은 파일 안에서 일어난다
  for (const m of modules) {
    const members = nodes.filter((n) => n.moduleId === m.id)
    const byFile = new Map<string, GraphNode[]>()
    for (const n of members) byFile.set(n.path, [...(byFile.get(n.path) ?? []), n])
    for (const file of byFile.values()) {
      const head = file[0]
      if (head.id !== m.hubNodeId) call(m.hubNodeId, head.id)
      file.slice(1).forEach((n, i) => call(r() < 0.7 ? head.id : file[1 + Math.floor(r() * (i + 1))].id, n.id))
    }
  }
  // 폴더 사이 호출은 적다: 진입점(api)과 몇몇 서비스 경로만
  call('api/router.py::dispatch', 'orders/controller.py::OrderController.place')
  call('api/router.py::dispatch', 'auth/session.py::require_login')
  call('api/router.py::dispatch', 'catalog/price.py::PriceRule.apply')
  call('orders/service.py::place_order', 'billing/invoice.py::InvoiceService.create')
  call('billing/invoice.py::send_receipt', 'notify/mailer.py::Mailer.deliver')
  call('orders/service.py::send_order_mail', 'notify/mailer.py::Mailer.deliver')
  call('auth/session.py::SessionStore.get', 'auth/session.py::refresh')
  for (let k = 0; k < 3 * scale; k++) { const m = pick(modules), o = pick(modules); if (m !== o) call(m.hubNodeId, pick(nodes.filter((n) => n.moduleId === o.id)).id) }

  // 의미·역사: 어긋남 견본 쌍, 그리고 폴더 안의 자연스러운 관계 몇 개
  for (const d of DIVERGENCE_SEEDS) {
    if (!d.target) continue
    const a = byId.get(d.source)!, b = byId.get(d.target)!
    if (d.type === 'duplicate') { b.semanticPosition = [a.semanticPosition[0] + 0.12, a.semanticPosition[1] + 0.08, a.semanticPosition[2] - 0.1]; edges.push({ source: a.id, target: b.id, kind: 'similar', weight: d.evidence.similarity ?? 0.8 }) }
    if (d.type === 'hidden_coupling') edges.push({ source: a.id, target: b.id, kind: 'cochange', weight: 0.7, since: '2025-06-02T00:00:00Z' })
  }
  for (const m of modules) {
    const members = nodes.filter((n) => n.moduleId === m.id)
    for (let k = 0; k < 2 * scale; k++) { const a = pick(members), b = pick(members); if (a !== b) edges.push({ source: a.id, target: b.id, kind: 'similar', weight: 0.6 + r() * 0.25 }) }
    for (let k = 0; k < 2 * scale; k++) { const a = pick(members), b = pick(members.filter((n) => n.path === a.path)); if (a !== b) edges.push({ source: a.id, target: b.id, kind: 'cochange', weight: 0.4 + r() * 0.4, since: since() }) }
  }
  return { jobId, stats: { functions: nodes.length, files: new Set(nodes.map((n) => n.path)).size, commits: 2000 }, modules, nodes, edges }
}

type Seed = Omit<Divergence, 'rank' | 'verdict'>

const ev = (similarity: number | null, structuralDistance: number | null, cochangeCount: number, s: number, t: number | null) =>
  ({ similarity, structuralDistance, cochangeCount, changeCounts: { source: s, target: t } })

export const DIVERGENCE_SEEDS: Seed[] = [
  { id: 'd_01', type: 'duplicate', score: 92, source: 'billing/invoice.py::calc_total', target: 'orders/cart.py::sum_items', moduleId: null, summary: 'orders/cart.py::sum_items', evidence: ev(0.92, null, 0, 23, 17) },
  { id: 'd_02', type: 'hidden_coupling', score: 88, source: 'auth/session.py::refresh', target: 'notify/mailer.py::render_template', moduleId: null, summary: 'notify/mailer.py::render_template', evidence: ev(0.21, null, 14, 19, 16) },
  { id: 'd_03', type: 'duplicate', score: 84, source: 'api/validators.py::check_email', target: 'auth/signup.py::validate_email', moduleId: null, summary: 'auth/signup.py::validate_email', evidence: ev(0.88, null, 1, 9, 12) },
  { id: 'd_04', type: 'mixed_responsibility', score: 79, source: 'orders/service.py::place_order', target: null, moduleId: 'orders/service.py', summary: '결제, 재고, 알림 로직이 한 모듈에', evidence: ev(null, 1, 0, 31, null) },
  { id: 'd_05', type: 'hidden_coupling', score: 74, source: 'catalog/price.py::apply_discount', target: 'billing/tax.py::rate_for', moduleId: null, summary: 'billing/tax.py::rate_for', evidence: ev(0.33, null, 9, 15, 11) },
  { id: 'd_06', type: 'duplicate', score: 71, source: 'notify/sms.py::format_phone', target: 'auth/profile.py::normalize_phone', moduleId: null, summary: 'auth/profile.py::normalize_phone', evidence: ev(0.83, 3, 0, 6, 8) },
  { id: 'd_07', type: 'hidden_coupling', score: 66, source: 'api/routes.py::export_csv', target: 'billing/report.py::to_rows', moduleId: null, summary: 'billing/report.py::to_rows', evidence: ev(0.4, null, 7, 12, 10) },
  { id: 'd_08', type: 'duplicate', score: 63, source: 'api/export.py::sum_rows', target: 'catalog/price.py::line_total', moduleId: null, summary: 'catalog/price.py::line_total', evidence: ev(0.79, null, 0, 4, 7) },
  { id: 'd_09', type: 'hidden_coupling', score: 61, source: 'api/router.py::dispatch', target: 'notify/mailer.py::send', moduleId: null, summary: 'notify/mailer.py::send', evidence: ev(0.18, 2, 4, 27, 13) },
  { id: 'd_10', type: 'mixed_responsibility', score: 55, source: 'api/router.py::dispatch', target: null, moduleId: 'api/router.py', summary: '라우팅, 권한 검사, 로깅이 한 파일에', evidence: ev(null, 1, 0, 27, null) },
  { id: 'd_11', type: 'duplicate', score: 48, source: 'billing/refund.py::refund_amount', target: 'billing/invoice.py::calc_total', moduleId: null, summary: 'billing/invoice.py::calc_total', evidence: ev(0.7, 2, 3, 5, 23) },
]

export function divergencesFor(jobId: string): Divergence[] {
  if (jobId.startsWith('j_tidy')) return []
  return DIVERGENCE_SEEDS.map((d, i) => ({ ...d, rank: i + 1, verdict: null }))
}

const KNOWN_CODE: Record<NodeId, { start: number; lastModified: string; code: string }> = {
  'billing/invoice.py::calc_total': { start: 41, lastModified: '2026-09-14T00:00:00Z', code: `
def calc_total(invoice, tax_rate):
    """Sum invoice lines with tax."""
    subtotal = 0
    for line in invoice.lines:
        price = line.unit_price * line.qty
        if line.discount:
            price -= price * line.discount
        subtotal += price
    tax = round(subtotal * tax_rate, 2)
    return subtotal + tax
` },
  'orders/cart.py::sum_items': { start: 112, lastModified: '2026-10-02T00:00:00Z', code: `
def sum_items(cart, region):
    total = 0
    for item in cart.items:
        amount = item.price * item.quantity
        if item.coupon:
            amount = amount * (1 - item.coupon.rate)
        total += amount
    vat = TAX_TABLE[region]
    return total + round(total * vat, 2)
` },
}

export function sourceFor(nodeId: NodeId): SourceCode {
  const known = KNOWN_CODE[nodeId]
  const name = nameOf(nodeId).split('.').pop()!
  const code = known ? known.code.replace(/^\n/, '') : `def ${name}(data):\n    """견본 코드: 실제 분석 결과가 아닙니다."""\n    result = []\n    for row in data:\n        if row is None:\n            continue\n        result.append(row)\n    return result\n`
  const start = known?.start ?? 10 + (hash(nodeId) % 120)
  const lines = code.split('\n').length - 1
  // 어긋남 근거의 수정 횟수와 같은 값을 쓴다
  const seed = DIVERGENCE_SEEDS.find((d) => d.source === nodeId || d.target === nodeId)
  const changeCount = seed ? (seed.source === nodeId ? seed.evidence.changeCounts.source : seed.evidence.changeCounts.target!) : 5 + (hash(nodeId) % 25)
  return { nodeId, path: pathOf(nodeId), lines: [start, start + lines - 1], language: 'python', code, changeCount, lastModified: known?.lastModified ?? '2026-10-02T00:00:00Z' }
}

export function timelineFor(jobId: string): Timeline {
  const r = rng(hash(jobId) + 7)
  const buckets = []
  for (let t = Date.UTC(2024, 2, 4); t <= Date.UTC(2026, 9, 26); t += 7 * 864e5) buckets.push({ date: new Date(t).toISOString(), commits: Math.round(3 + r() ** 1.8 * 24) })
  return { from: buckets[0].date, to: buckets[buckets.length - 1].date, buckets }
}
