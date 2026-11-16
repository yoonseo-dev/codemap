import { Billboard, Html, OrbitControls } from '@react-three/drei'
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as THREE from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import type { EdgeKind, Graph, LayoutMode, MapLayer, NodeId } from '../../api'
import { RADIUS, type Layouts } from './useLayouts'
import styles from './MapScene.module.css'

export type CameraCommand = { kind: 'zoomIn' | 'zoomOut' | 'fit'; n: number }

export interface SceneFocus {
  /** 고리와 이름표를 다는 주인공 (어긋남 쌍 또는 고른 함수) */
  primary: NodeId[]
  /** 밝게 남길 함수 (주인공 + 이웃) */
  nodes: NodeId[]
  /** 주인공 사이에 그릴 설명 상자 */
  callout?: ReactNode
}

interface Props {
  graph: Graph
  layouts: Layouts
  mode: LayoutMode
  layers: Record<MapLayer, boolean>
  focus: SceneFocus | null
  hovered: NodeId | null
  onHover: (id: NodeId | null) => void
  onSelectNode: (id: NodeId | null) => void
  command: CameraCommand | null
  /** true면 왼쪽 끌기가 화면 이동 (Space를 누른 채이거나 이동 도구를 켠 상태) */
  pan: boolean
}

const LAYER_OF: Record<EdgeKind, MapLayer> = { call: 'structure', import: 'structure', similar: 'semantic', cochange: 'history' }
const CURVE_SEGMENTS = 8
const TRANSITION = 0.9

const token = (name: string) => new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue(name).trim())
const ease = (t: number) => 1 - Math.pow(1 - t, 3)
const nodeSize = (degree: number) => 0.06 + Math.sqrt(degree) * 0.028

function useColors() {
  return useMemo(() => ({
    bg: token('--color-bg-canvas'),
    structure: token('--color-map-structure'),
    semantic: token('--color-map-semantic'),
    history: token('--color-map-history'),
    primary: token('--color-text-primary'),
  }), [])
}

/** 선 하나를 좌표 배열에 쓴다. 역사 선은 휘어진 곡선(여러 조각) */
function writeEdge(out: Float32Array, o: number, pos: Float32Array, a: number, b: number, curved: boolean) {
  const ax = pos[a * 3], ay = pos[a * 3 + 1], az = pos[a * 3 + 2]
  const bx = pos[b * 3], by = pos[b * 3 + 1], bz = pos[b * 3 + 2]
  if (!curved) { out.set([ax, ay, az, bx, by, bz], o); return o + 6 }
  const len = Math.hypot(bx - ax, by - ay, bz - az)
  const mx = (ax + bx) / 2, my = (ay + by) / 2 + len * 0.25, mz = (az + bz) / 2
  let px = ax, py = ay, pz = az
  for (let s = 1; s <= CURVE_SEGMENTS; s++) {
    const t = s / CURVE_SEGMENTS, u = 1 - t
    const x = u * u * ax + 2 * u * t * mx + t * t * bx, y = u * u * ay + 2 * u * t * my + t * t * by, z = u * u * az + 2 * u * t * mz + t * t * bz
    out.set([px, py, pz, x, y, z], o); o += 6
    px = x; py = y; pz = z
  }
  return o
}

function Scene({ graph, layouts, mode, layers, focus, hovered, onHover, onSelectNode, command, pan }: Props) {
  const colors = useColors()
  const index = useMemo(() => new Map(graph.nodes.map((n, i) => [n.id, i])), [graph])
  const edges = useMemo(() => graph.edges.map((e) => ({ a: index.get(e.source)!, b: index.get(e.target)!, kind: e.kind, layer: LAYER_OF[e.kind] }))
    .filter((e) => e.a !== undefined && e.b !== undefined), [graph, index])
  const hubs = useMemo(() => graph.modules.map((m) => index.get(m.hubNodeId)!).filter((i) => i !== undefined), [graph, index])

  const focusSet = useMemo(() => new Set((focus?.nodes ?? []).map((id) => index.get(id)!)), [focus, index])
  const primarySet = useMemo(() => new Set((focus?.primary ?? []).map((id) => index.get(id)!)), [focus, index])
  const active = focusSet.size > 0
  const highlighted = useMemo(() => edges.filter((e) => active && focusSet.has(e.a) && focusSet.has(e.b) && (primarySet.has(e.a) || primarySet.has(e.b))), [edges, active, focusSet, primarySet])

  // ---- 좌표: 보기 전환 시 이전 좌표에서 새 좌표로 옮겨 간다 ----
  const target = mode === 'structure' && layouts.structure ? layouts.structure : layouts.semantic
  const current = useRef<Float32Array>(target.slice())
  const from = useRef<Float32Array>(target.slice())
  const t = useRef(1)
  const dirty = useRef(true)
  useEffect(() => {
    if (current.current.length !== target.length) { current.current = target.slice(); from.current = target.slice(); t.current = 1; dirty.current = true; return }
    from.current = current.current.slice(); t.current = 0
  }, [target])

  // ---- 점 ----
  const nodesRef = useRef<THREE.InstancedMesh>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])
  useLayoutEffect(() => {
    const mesh = nodesRef.current
    if (!mesh) return
    const c = new THREE.Color()
    graph.nodes.forEach((_, i) => {
      const on = !active || focusSet.has(i)
      c.copy(primarySet.has(i) ? colors.primary : colors.structure)
      if (!on) c.lerp(colors.bg, 0.82)
      mesh.setColorAt(i, c)
    })
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    dirty.current = true
  }, [graph, active, focusSet, primarySet, colors])

  // ---- 선: 종류별 기본 묶음 + 강조 묶음 ----
  const groups = useMemo(() => (['structure', 'semantic', 'history'] as MapLayer[]).map((layer) => {
    const list = edges.filter((e) => e.layer === layer)
    const curved = layer === 'history'
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(list.length * (curved ? CURVE_SEGMENTS : 1) * 6), 3))
    return { layer, list, curved, geo }
  }), [edges])
  const hiGeo = useMemo(() => {
    const segs = highlighted.reduce((s, e) => s + (e.layer === 'history' ? CURVE_SEGMENTS : 1), 0)
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(segs * 6), 3))
    const col = new Float32Array(segs * 6)
    let o = 0
    for (const e of highlighted) {
      const c = e.layer === 'structure' ? colors.structure : e.layer === 'semantic' ? colors.semantic : colors.history
      for (let s = 0; s < (e.layer === 'history' ? CURVE_SEGMENTS : 1) * 2; s++) { col.set([c.r, c.g, c.b], o); o += 3 }
    }
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
    dirty.current = true
    return geo
  }, [highlighted, colors])
  const semanticLines = useRef<THREE.LineSegments>(null)
  useEffect(() => () => { groups.forEach((g) => g.geo.dispose()) }, [groups])
  useEffect(() => () => hiGeo.dispose(), [hiGeo])

  // ---- 고리(폴더 대표, 주인공) ----
  const hubRings = useRef<(THREE.Object3D | null)[]>([])
  const primaryList = useMemo(() => [...primarySet], [primarySet])
  const primaryRings = useRef<(THREE.Object3D | null)[]>([])

  // ---- 카메라 ----
  const controls = useRef<OrbitControlsImpl>(null)
  const camera = useThree((s) => s.camera)
  const goal = useRef<{ target: THREE.Vector3; distance: number } | null>({ target: new THREE.Vector3(), distance: RADIUS * 2.7 })
  const centerOf = (ids: number[], pos: Float32Array) => {
    const v = new THREE.Vector3()
    for (const i of ids) v.add(new THREE.Vector3(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]))
    return v.divideScalar(Math.max(1, ids.length))
  }
  const focusKey = focus?.primary.join('|') ?? ''
  useEffect(() => {
    if (!primaryList.length) return
    const c = centerOf(primaryList, target)
    let spread = 0
    for (const i of primaryList) spread = Math.max(spread, c.distanceTo(new THREE.Vector3(target[i * 3], target[i * 3 + 1], target[i * 3 + 2])))
    goal.current = { target: c, distance: Math.max(20, spread * 2.6) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusKey, target])
  useEffect(() => {
    if (!command) return
    const ctl = controls.current
    const dist = ctl ? camera.position.distanceTo(ctl.target) : RADIUS * 2.7
    if (command.kind === 'fit') goal.current = { target: new THREE.Vector3(), distance: RADIUS * 2.7 }
    else goal.current = { target: ctl ? ctl.target.clone() : new THREE.Vector3(), distance: dist * (command.kind === 'zoomIn' ? 0.7 : 1.4) }
  }, [command, camera])

  useFrame((_, delta) => {
    // 좌표 보간
    if (t.current < 1) {
      t.current = Math.min(1, t.current + delta / TRANSITION)
      const k = ease(t.current), cur = current.current, a = from.current
      for (let i = 0; i < cur.length; i++) cur[i] = a[i] + (target[i] - a[i]) * k
      dirty.current = true
    }
    if (dirty.current) {
      dirty.current = false
      const pos = current.current
      const mesh = nodesRef.current
      if (mesh) {
        graph.nodes.forEach((n, i) => {
          const s = nodeSize(n.degree) * (primarySet.has(i) ? 1.6 : 1)
          dummy.position.set(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]); dummy.scale.setScalar(s); dummy.updateMatrix()
          mesh.setMatrixAt(i, dummy.matrix)
        })
        mesh.instanceMatrix.needsUpdate = true
        mesh.computeBoundingSphere()
      }
      for (const g of groups) {
        const arr = g.geo.attributes.position.array as Float32Array
        let o = 0
        for (const e of g.list) o = writeEdge(arr, o, pos, e.a, e.b, g.curved)
        g.geo.attributes.position.needsUpdate = true
        g.geo.computeBoundingSphere()
      }
      semanticLines.current?.computeLineDistances()
      const hi = hiGeo.attributes.position.array as Float32Array
      let o = 0
      for (const e of highlighted) o = writeEdge(hi, o, pos, e.a, e.b, e.layer === 'history')
      hiGeo.attributes.position.needsUpdate = true
      hiGeo.computeBoundingSphere()
      hubs.forEach((h, k) => hubRings.current[k]?.position.set(pos[h * 3], pos[h * 3 + 1], pos[h * 3 + 2]))
      primaryList.forEach((p, k) => primaryRings.current[k]?.position.set(pos[p * 3], pos[p * 3 + 1], pos[p * 3 + 2]))
    }
    // 카메라 이동
    const ctl = controls.current
    const g = goal.current
    if (ctl && g) {
      const k = 1 - Math.pow(0.0015, delta)
      ctl.target.lerp(g.target, k)
      const dir = camera.position.clone().sub(ctl.target).normalize()
      const want = ctl.target.clone().add(dir.multiplyScalar(g.distance))
      camera.position.lerp(want, k)
      if (ctl.target.distanceTo(g.target) < 0.01 && Math.abs(camera.position.distanceTo(ctl.target) - g.distance) < 0.05) goal.current = null
      ctl.update()
    }
  })

  // ---- 이름표 위치: 도착 좌표 기준 ----
  const labelPos = (i: number): [number, number, number] => [target[i * 3], target[i * 3 + 1], target[i * 3 + 2]]
  const moduleLabels = useMemo(() => graph.modules.map((m) => {
    const ids = graph.nodes.flatMap((n, i) => (n.moduleId === m.id ? [i] : []))
    const c = centerOf(ids, target)
    let top = -Infinity
    for (const i of ids) top = Math.max(top, target[i * 3 + 1])
    const hub = graph.nodes[index.get(m.hubNodeId)!]
    return { id: m.id, pos: [c.x, top + 0.8, c.z] as [number, number, number], hub: hub?.name }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [graph, target, index])
  const hoveredIndex = hovered ? index.get(hovered) : undefined

  const onMove = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation()
    const id = e.instanceId !== undefined ? graph.nodes[e.instanceId].id : null
    if (id !== hovered) onHover(id)
  }

  const fade = (base: number) => (active ? 0.06 : base)

  return (
    <>
      <color attach="background" args={[colors.bg]} />
      <fog attach="fog" args={[colors.bg, RADIUS * 1.6, RADIUS * 4.2]} />
      {/* 왼쪽 끌기는 돌리기, Space를 누른 채(이동 도구)면 이동. 가운데·오른쪽 버튼 끌기는 항상 이동 (Figma와 같음) */}
      <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={0.08} minDistance={3} maxDistance={RADIUS * 6}
        screenSpacePanning
        mouseButtons={{ LEFT: pan ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.PAN }}
        touches={{ ONE: pan ? THREE.TOUCH.PAN : THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN }}
        onStart={() => { goal.current = null }} />

      {groups.map((g) => (
        g.layer === 'semantic' ? (
          <lineSegments key={g.layer} ref={semanticLines} geometry={g.geo} visible={layers.semantic} raycast={() => null}>
            <lineDashedMaterial color={colors.semantic} dashSize={0.25} gapSize={0.2} transparent opacity={fade(0.55)} depthWrite={false} />
          </lineSegments>
        ) : (
          <lineSegments key={g.layer} geometry={g.geo} visible={layers[g.layer]} raycast={() => null}>
            <lineBasicMaterial color={g.layer === 'structure' ? colors.structure : colors.history} transparent opacity={fade(g.layer === 'structure' ? 0.22 : 0.5)} depthWrite={false} />
          </lineSegments>
        )
      ))}
      <lineSegments geometry={hiGeo} raycast={() => null} renderOrder={2}>
        <lineBasicMaterial vertexColors transparent opacity={0.95} depthWrite={false} />
      </lineSegments>

      <instancedMesh ref={nodesRef} args={[undefined, undefined, graph.nodes.length]} onPointerMove={onMove} onPointerOut={() => onHover(null)}
        onClick={(e) => { e.stopPropagation(); if (e.instanceId !== undefined) onSelectNode(graph.nodes[e.instanceId].id) }}>
        <sphereGeometry args={[1, 12, 10]} />
        <meshBasicMaterial />
      </instancedMesh>

      {hubs.map((h, k) => (
        <Billboard key={h} ref={(el) => { hubRings.current[k] = el }}>
          <mesh raycast={() => null}>
            <ringGeometry args={[nodeSize(graph.nodes[h].degree) * 1.6, nodeSize(graph.nodes[h].degree) * 1.6 + 0.05, 40]} />
            <meshBasicMaterial color={colors.structure} transparent opacity={active && !focusSet.has(h) ? 0.15 : 0.9} />
          </mesh>
        </Billboard>
      ))}
      {primaryList.map((p, k) => (
        <Billboard key={p} ref={(el) => { primaryRings.current[k] = el }}>
          <mesh raycast={() => null}><ringGeometry args={[0.32, 0.35, 48]} /><meshBasicMaterial color={colors.primary} /></mesh>
          <mesh raycast={() => null}><ringGeometry args={[0.55, 0.57, 48]} /><meshBasicMaterial color={colors.primary} transparent opacity={0.35} /></mesh>
        </Billboard>
      ))}

      {moduleLabels.map((m) => (
        <Html key={m.id} position={m.pos} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
          <div className={`${styles.moduleLabel} ${active ? styles.faded : ''}`}>
            <span>{m.id}</span>
            {m.hub && <span className={styles.hubName}>{m.hub}</span>}
          </div>
        </Html>
      ))}
      {primaryList.map((p) => (
        <Html key={p} position={labelPos(p)} zIndexRange={[30, 20]} style={{ pointerEvents: 'none' }}>
          <div className={styles.focusLabel}>{graph.nodes[p].path}::{graph.nodes[p].name}</div>
        </Html>
      ))}
      {focus?.callout && primaryList.length > 0 && (
        <Html position={centerOf(primaryList, target).add(new THREE.Vector3(0, -2.6, 0)).toArray() as [number, number, number]} center zIndexRange={[30, 20]} style={{ pointerEvents: 'none' }}>
          {focus.callout}
        </Html>
      )}
      {hoveredIndex !== undefined && (
        <Html position={labelPos(hoveredIndex)} zIndexRange={[40, 30]} style={{ pointerEvents: 'none' }}>
          <div className={styles.tooltip}>
            <span className="mono">{graph.nodes[hoveredIndex].path}::{graph.nodes[hoveredIndex].name}</span>
            <span>연결 {graph.nodes[hoveredIndex].degree}개, 눌러서 선택</span>
          </div>
        </Html>
      )}
    </>
  )
}

/** 개발 모드에서만: 성능 측정 스크립트가 렌더러에 닿을 수 있게 */
function DevHandle() {
  const state = useThree()
  useEffect(() => {
    if (import.meta.env.DEV) (window as unknown as { __codemap3d: unknown }).__codemap3d = state
  }, [state])
  return null
}

const isTyping = (t: EventTarget | null) => t instanceof Element && !!t.closest('input, textarea, button, a, [role="radio"], [contenteditable="true"]')

export function MapScene(props: Omit<Props, 'pan'> & { label: string; onBackground: () => void; hand?: boolean }) {
  const { label, onBackground, hand = false, ...rest } = props
  // Space를 누르고 있는 동안만 이동 도구
  const [space, setSpace] = useState(false)
  useEffect(() => {
    const down = (e: KeyboardEvent) => { if (e.code !== 'Space' || isTyping(e.target)) return; e.preventDefault(); setSpace(true) }
    const up = (e: KeyboardEvent) => { if (e.code === 'Space') setSpace(false) }
    const release = () => setSpace(false)
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', release)
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); window.removeEventListener('blur', release) }
  }, [])
  const pan = hand || space
  return (
    <div className={styles.wrap} role="img" aria-label={label} data-pan={pan} data-hover={props.hovered ? 'true' : 'false'}>
      <Canvas camera={{ position: [0, RADIUS * 0.6, RADIUS * 2.6], fov: 45, near: 0.1, far: 400 }} dpr={[1, 2]}
        onPointerMissed={onBackground}>
        <Scene {...rest} pan={pan} />
        {import.meta.env.DEV && <DevHandle />}
      </Canvas>
    </div>
  )
}
