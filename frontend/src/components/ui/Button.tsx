import type { ButtonHTMLAttributes } from 'react'
import styles from './Button.module.css'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary'
  /** 랜딩처럼 페이지 화면에서는 44px, 앱 화면은 36px */
  size?: 'app' | 'page'
  block?: boolean
}

export function Button({ variant = 'secondary', size = 'app', block, className, type = 'button', ...rest }: Props) {
  const cls = [styles.button, styles[variant], styles[size], block && styles.block, className].filter(Boolean).join(' ')
  return <button type={type} className={cls} {...rest} />
}
