import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type DivergenceType, type EdgeKind, type LayoutMode, type MapLayer, type NodeId } from '../../api'
import { DivergenceItem } from '../../components/divergence/DivergenceItem'
import { MapScene, type CameraCommand, type SceneFocus } from '../../components/graph3d/MapScene'
import { useLayouts } from '../../components/graph3d/useLayouts'
import { TopBar } from '../../components/layout/TopBar'
import { Button } from '../../components/ui/Button'
import { FocusIcon, MinusIcon, MoveIcon, PlusIcon } from '../../components/ui/icons'
import { Kbd } from '../../components/ui/Kbd'
import { Segmented } from '../../components/ui/Segmented'
import { DIVERGENCE_TYPE, num } from '../../lib/labels'
import { NodePanel } from './NodePanel'
import styles from './MapPage.module.css'

type Filter = 'all' | DivergenceType
const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'duplicate', label: '중복' },
  { value: 'hidden_coupling', label: '숨은 결합' },
  { value: 'mixed_responsibility', label: '책임 혼재' },
]
const DEFAULT_MIN = 60
const LOW_MIN = 40
const LAYER_OF: Record<EdgeKind, MapLayer> = { call: 'structure', import: 'structure', similar: 'semantic', cochange: 'history' }
const LAYERS: { layer: MapLayer; label: string; swatch: string }[] = [
  { layer: 'structure', label: '구조: 서로 호출함', swatch: 'structure' },
  { layer: 'semantic', label: '의미: 하는 일이 비슷함', swatch: 'semantic' },
  { layer: 'history', label: '역사: 같이 수정됨', swatch: 'history' },
]

type Selection = { kind: 'divergence'; id: string } | { kind: 'node'; id: NodeId } | null

export function MapPage() {
  const { jobId = '' } = useParams()
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('all')
  const [minScore, setMinScore] = useState(DEFAULT_MIN)
  const [selection, setSelection] = useState<Selection>(null)
  const [mode, setMode] = useState<LayoutMode>('structure')
  // 처음에는 단순하게: 구조 선만
  const [layers, setLayers] = useState<Record<MapLayer, boolean>>({ structure: true, semantic: false, history: false })
  const [hovered, setHovered] = useState<NodeId | null>(null)
  const [command, setCommand] = useState<CameraCommand | null>(null)
  // 이동 도구를 켜 두는 상태. 평소에는 Space를 누르는 동안만 켜진다
  const [hand, setHand] = useState(false)
  const listRef = useRef<HTMLUListElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== 'h' || e.ctrlKey || e.metaKey || e.altKey) return
      if (e.target instanceof Element && e.target.closest('input, textarea, [contenteditable="true"]')) return
      setHand((v) => !v)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const job = useQuery({ queryKey: ['job', jobId], queryFn: () => api.getJob(jobId) })
  const graph = useQuery({ queryKey: ['graph', jobId], queryFn: () => api.getGraph(jobId) })
  const layouts = useLayouts(graph.data)
  const divergences = useQuery({
    queryKey: ['divergences', jobId, filter, minScore],
    queryFn: () => api.listDivergences(jobId, { type: filter === 'all' ? undefined : filter, minScore, limit: 200 }),
  })
  const items = divergences.data?.items ?? []
  const selectedDivergenceId = selection?.kind === 'divergence' ? selection.id : null
  // 처음에는 아무것도 고르지 않은 전체 지도. 목록이나 점을 직접 골라야 그 부분이 강조된다
  const current = items.find((d) => d.id === selectedDivergenceId) ?? null

  const counts = useMemo(() => {
    const c: Record<MapLayer, number> = { structure: 0, semantic: 0, history: 0 }
    for (const e of graph.data?.edges ?? []) c[LAYER_OF[e.kind]]++
    return c
  }, [graph.data])

  // 지도에서 밝게 남길 것
  const focus = useMemo<SceneFocus | null>(() => {
    const g = graph.data
    if (!g) return null
    const neighbors = (ids: NodeId[], all: boolean) => {
      const set = new Set(ids)
      for (const e of g.edges) {
        if (!all && LAYER_OF[e.kind] !== 'structure') continue
        if (ids.includes(e.source)) set.add(e.target)
        if (ids.includes(e.target)) set.add(e.source)
      }
      return [...set]
    }
    if (selection?.kind === 'node') return { primary: [selection.id], nodes: neighbors([selection.id], true) }
    if (!current) return null
    const primary = current.target ? [current.source, current.target] : [current.source]
    const type = DIVERGENCE_TYPE[current.type]
    const e = current.evidence
    const facts = [
      e.similarity !== null && `하는 일 유사도 ${e.similarity.toFixed(2)}`,
      e.structuralDistance === null ? '호출 연결 없음' : `호출 ${e.structuralDistance}단계`,
      `같이 수정 ${e.cochangeCount}회`,
    ].filter(Boolean).join(', ')
    return {
      primary,
      nodes: [...neighbors(primary, false), ...primary],
      callout: (
        <div className={styles.callout} style={{ borderColor: type.color }}>
          <span style={{ color: type.color }}>{type.label} 의심, 의심도 {current.score}</span>
          <span>{facts}</span>
        </div>
      ),
    }
  }, [graph.data, selection, current])

  const open = (id: string) => navigate(`/jobs/${jobId}/divergences/${id}`)
  const move = (dir: number) => {
    const i = items.findIndex((d) => d.id === current?.id)
    const next = i < 0 ? items[0] : items[Math.min(items.length - 1, Math.max(0, i + dir))]
    if (!next) return
    setSelection({ kind: 'divergence', id: next.id })
    listRef.current?.querySelector<HTMLButtonElement>(`[data-divergence-id="${next.id}"]`)?.focus()
  }
  const cam = (kind: CameraCommand['kind']) => setCommand((c) => ({ kind, n: (c?.n ?? 0) + 1 }))
  const ready = graph.data && layouts && (mode === 'semantic' || layouts.structure)

  return (
    <div className={styles.screen}>
      <TopBar repository={job.data?.repository} commit={job.data?.commit} mode={{ value: mode, onChange: setMode }} />
      <div className={styles.body}>
        <main className={styles.canvas} aria-label="코드 지도">
          {graph.data && layouts && (
            <MapScene graph={graph.data} layouts={layouts} mode={mode} layers={layers} focus={focus}
              hovered={hovered} onHover={setHovered} command={command} hand={hand}
              onSelectNode={(id) => setSelection(id ? { kind: 'node', id } : null)}
              onBackground={() => { if (selection?.kind === 'node') setSelection(null) }}
              label={`함수 ${graph.data.nodes.length}개의 연결 지도. 오른쪽 목록이나 함수를 고르면 관련된 부분만 밝게 표시됩니다.`} />
          )}

          {!ready && !graph.isError && (
            <div className={styles.loading} role="status">
              <p className={styles.loadingTitle}>지도를 그리는 중이에요</p>
              <p className={styles.muted}>{graph.data ? `함수 ${num(graph.data.nodes.length)}개의 자리를 계산하고 있어요` : '지도 데이터를 받고 있어요'}</p>
              <div className={styles.loadingTrack}><div /></div>
            </div>
          )}
          {graph.isError && (
            <div className={styles.loading} role="alert">
              <p className={styles.loadingTitle}>지도를 불러오지 못했어요</p>
              <Button onClick={() => graph.refetch()}>다시 불러오기</Button>
            </div>
          )}

          {graph.data && (
            <>
              <div className={styles.legend}>
                <h2 className={styles.sectionLabel}>선 종류</h2>
                {LAYERS.map((l) => (
                  <button key={l.layer} type="button" className={styles.layer} aria-pressed={layers[l.layer]}
                    onClick={() => setLayers((s) => ({ ...s, [l.layer]: !s[l.layer] }))}>
                    <svg width="18" height="8" viewBox="0 0 18 8" aria-hidden="true">
                      {l.layer === 'history' ? <path d="M1 7 Q9 -1 17 7" className={styles[l.swatch]} /> : <line x1="0" y1="4" x2="18" y2="4" className={styles[l.swatch]} />}
                    </svg>
                    <span className={styles.layerLabel}>{l.label}</span>
                    <span className="mono num">{num(counts[l.layer])}</span>
                  </button>
                ))}
                <p className={styles.legendNote}>점 크기는 연결 수, 고리는 폴더 대표 함수예요. 점을 누르면 이어진 것만 밝게 보여요.</p>
                <p className={styles.legendNote}>끌면 돌리기, <Kbd>Space</Kbd>를 누른 채 끌면 이동, 휠은 확대와 축소예요.</p>
              </div>
              <p className={styles.stats}>함수 {num(graph.data.stats.functions)}개, 파일 {num(graph.data.stats.files)}개</p>
              <div className={styles.camera} role="group" aria-label="카메라">
                <button type="button" aria-label="이동 도구 (H)" title="이동 도구 (H)" aria-pressed={hand} onClick={() => setHand((v) => !v)}><MoveIcon /></button>
                <button type="button" aria-label="확대" onClick={() => cam('zoomIn')}><PlusIcon /></button>
                <button type="button" aria-label="축소" onClick={() => cam('zoomOut')}><MinusIcon /></button>
                <button type="button" aria-label="전체 보기" onClick={() => cam('fit')}><FocusIcon /></button>
              </div>
            </>
          )}
        </main>

        <aside className={styles.panel} aria-label={selection?.kind === 'node' ? '함수 정보' : '어긋남 목록'}>
          {selection?.kind === 'node' ? (
            <NodePanel jobId={jobId} nodeId={selection.id} onBack={() => setSelection(null)}
              onSelectNode={(id) => setSelection({ kind: 'node', id })}
              onSelectDivergence={(id) => setSelection({ kind: 'divergence', id })} onOpenDivergence={open} />
          ) : (
            <>
              <div className={styles.panelHead}>
                <h2 className={styles.title}>
                  어긋남 <span className={`mono num ${styles.count}`}>{divergences.data ? divergences.data.total : ''}</span>
                </h2>
                <p className={styles.muted}>세 지도가 서로 다르게 말하는 함수 쌍을 의심도 높은 순으로</p>
                <Segmented label="유형" look="plain" value={filter} onChange={(f) => { setFilter(f); setSelection(null) }} options={FILTERS} />
                {items.length > 0 && <p className={styles.keys}><Kbd>↑ ↓</Kbd> 목록 이동 <Kbd>Enter</Kbd> 코드 비교</p>}
              </div>

              <div className={styles.listWrap}>
                {divergences.isPending && (
                  <ul className={styles.list} aria-hidden="true">
                    {Array.from({ length: 6 }, (_, i) => (
                      <li key={i} className={styles.skeleton}><span style={{ width: 90 }} /><span style={{ width: 220 }} /><span style={{ width: 170 }} /></li>
                    ))}
                  </ul>
                )}
                {divergences.isError && (
                  <div className={styles.empty} role="alert">
                    <p className={styles.emptyTitle}>목록을 불러오지 못했어요</p>
                    <Button onClick={() => divergences.refetch()}>다시 불러오기</Button>
                  </div>
                )}
                {divergences.data && items.length === 0 && (
                  <div className={styles.empty}>
                    <p className={styles.emptyTitle}>어긋남을 찾지 못했어요</p>
                    <p className={styles.muted}>
                      세 지도가 대체로 같은 이야기를 하고 있어요. 지금 기준(의심도 {divergences.data.minScore} 이상)을 넘는 함수 쌍이 없습니다.
                      {minScore > LOW_MIN && ' 기준을 낮추면 약한 신호까지 볼 수 있어요.'}
                    </p>
                    {minScore > LOW_MIN && <Button onClick={() => setMinScore(LOW_MIN)}>의심도 {LOW_MIN} 이상으로 다시 보기</Button>}
                  </div>
                )}
                {items.length > 0 && (
                  <ul ref={listRef} className={styles.list}
                    onKeyDown={(e) => {
                      if (e.key === 'ArrowDown') { e.preventDefault(); move(1) }
                      if (e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
                      if (e.key === 'Enter' && current) { e.preventDefault(); open(current.id) }
                    }}>
                    {items.map((d) => (
                      <DivergenceItem key={d.id} d={d} selected={d.id === current?.id} onSelect={() => setSelection({ kind: 'divergence', id: d.id })} onOpen={() => open(d.id)} />
                    ))}
                  </ul>
                )}
              </div>

              {current && (
                <div className={styles.panelFoot}>
                  <Button variant="primary" block onClick={() => open(current.id)}>{current.target ? '두 함수 코드 비교하기' : '코드 보기'}</Button>
                </div>
              )}
            </>
          )}
        </aside>
      </div>
    </div>
  )
}
