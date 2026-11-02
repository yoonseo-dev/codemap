export type MapKind = 'structure' | 'semantic' | 'history'

export interface GraphNode {
  id: string
  label: string
  /** 의미 모드에서 쓰는 UMAP 3D 좌표 */
  umap?: [number, number, number]
}

export interface GraphEdge {
  source: string
  target: string
  kind: MapKind
  weight: number
}
