import styles from './Segmented.module.css'

interface Props<T extends string> {
  label: string
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
  /** framed: 테두리 있는 묶음(상단 바), plain: 테두리 없이(필터) */
  look?: 'framed' | 'plain'
}

/** 하나만 고르는 버튼 묶음. 화살표 키로 옮겨 다닐 수 있다 */
export function Segmented<T extends string>({ label, options, value, onChange, look = 'framed' }: Props<T>) {
  const move = (dir: number) => {
    const i = options.findIndex((o) => o.value === value)
    onChange(options[(i + dir + options.length) % options.length].value)
  }
  return (
    <div role="radiogroup" aria-label={label} className={`${styles.group} ${styles[look]}`}
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight') { e.preventDefault(); move(1) }
        if (e.key === 'ArrowLeft') { e.preventDefault(); move(-1) }
      }}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1} className={styles.item} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}
