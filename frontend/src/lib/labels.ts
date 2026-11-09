import type { DivergenceType, StageName } from '../api'

export const DIVERGENCE_TYPE: Record<DivergenceType, { label: string; meaning: string; color: string }> = {
  duplicate: { label: '중복 구현', meaning: '같은 일을 두 곳에서 따로 함', color: 'var(--color-map-semantic)' },
  hidden_coupling: { label: '숨은 결합', meaning: '안 부르는데 늘 같이 고쳐짐', color: 'var(--color-map-history)' },
  mixed_responsibility: { label: '책임 혼재', meaning: '한 파일이 여러 일을 맡음', color: 'var(--color-divergence-mixed)' },
}

export const STAGE_LABEL: Record<StageName, string> = {
  INGEST: '수집',
  STRUCTURE: '구조 지도',
  SEMANTIC: '의미 지도',
  HISTORY: '역사 지도',
  DIVERGENCE: '어긋남 탐지',
}

/** 2026-10-28 */
export const ymd = (iso: string) => iso.slice(0, 10)

/** 10-28 */
export const md = (iso: string) => iso.slice(5, 10)

export const num = (n: number) => n.toLocaleString('ko-KR')
