import type { CodemapApi } from './client'
import { httpApi } from './http'
import { mockApi } from './mock/mockApi'

/** VITE_API=http 이면 실제 백엔드, 아니면 브라우저 안의 가짜 API */
export const api: CodemapApi = import.meta.env.VITE_API === 'http' ? httpApi : mockApi

export { ApiRequestError } from './client'
export * from './types'
