import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import type { DivergenceType, LayoutMode, MapLayer, NodeId } from '../api'

export type Filter = 'all' | DivergenceType
export type Selection = { kind: 'divergence'; id: string } | { kind: 'node'; id: NodeId } | null

/** 지도 화면의 보기 상태. 코드 비교 화면에 다녀와도 그대로여야 하므로 화면(컴포넌트) 밖에 둔다. */
export interface MapView {
  mode: LayoutMode
  layers: Record<MapLayer, boolean>
  filter: Filter
  minScore: number
  selection: Selection
}

export const DEFAULT_MIN_SCORE = 60

export const DEFAULT_VIEW: MapView = {
  mode: 'structure',
  // 처음에는 단순하게: 구조 선만
  layers: { structure: true, semantic: false, history: false },
  filter: 'all',
  minScore: DEFAULT_MIN_SCORE,
  selection: null,
}

interface Store {
  /** 작업(jobId)마다 따로 기억한다 */
  views: Record<string, MapView>
  patch: (jobId: string, change: Partial<MapView>) => void
}

export const useMapView = create<Store>()(
  persist(
    (set) => ({
      views: {},
      patch: (jobId, change) =>
        set((s) => ({ views: { ...s.views, [jobId]: { ...(s.views[jobId] ?? DEFAULT_VIEW), ...change } } })),
    }),
    {
      name: 'codemap.mapView',
      // 탭을 닫으면 사라진다. 새로고침에는 살아남는다.
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
)
