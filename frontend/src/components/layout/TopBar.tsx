import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { CommitRef, LayoutMode, Repository } from '../../api'
import { ymd } from '../../lib/labels'
import { Kbd } from '../ui/Kbd'
import { SearchIcon } from '../ui/icons'
import { Segmented } from '../ui/Segmented'
import styles from './TopBar.module.css'

interface Props {
  repository?: Repository
  commit?: CommitRef | null
  /** 지도 화면에서만 넘긴다 */
  mode?: { value: LayoutMode; onChange: (m: LayoutMode) => void }
  onSearch?: () => void
  actions?: ReactNode
}

export function TopBar({ repository, commit, mode, onSearch, actions }: Props) {
  return (
    <header className={styles.bar}>
      <div className={styles.left}>
        <Link to="/" className={styles.wordmark}>Codemap</Link>
        {repository && (
          <>
            <span className={styles.divider} aria-hidden="true" />
            <span className="mono">{repository.owner}/{repository.name}</span>
            {commit && <span className={styles.commit}>{ymd(commit.date)} 커밋 <span className="mono">{commit.sha}</span></span>}
          </>
        )}
      </div>
      <div className={styles.center}>
        {mode && (
          <Segmented label="보기" value={mode.value} onChange={mode.onChange}
            options={[{ value: 'structure', label: '폴더별 보기' }, { value: 'semantic', label: '하는 일별 보기' }]} />
        )}
      </div>
      <div className={styles.right}>
        {onSearch && (
          <button type="button" className={styles.search} onClick={onSearch}>
            <SearchIcon />
            <span className={styles.searchLabel}>함수 찾기</span>
            <Kbd>Ctrl K</Kbd>
          </button>
        )}
        {actions}
      </div>
    </header>
  )
}
