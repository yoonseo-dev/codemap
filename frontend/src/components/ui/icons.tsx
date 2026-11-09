import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function Icon({ size = 16, children, ...rest }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      {children}
    </svg>
  )
}

export const SearchIcon = (p: IconProps) => <Icon {...p}><circle cx="10" cy="10" r="6" /><path d="M15 15l5 5" /></Icon>
export const ArrowLeftIcon = (p: IconProps) => <Icon {...p}><path d="M5 12h14M5 12l6 6M5 12l6-6" /></Icon>
export const AlertIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16h.01" /></Icon>
export const PlusIcon = (p: IconProps) => <Icon {...p}><path d="M12 5v14M5 12h14" /></Icon>
export const MinusIcon = (p: IconProps) => <Icon {...p}><path d="M5 12h14" /></Icon>
export const FocusIcon = (p: IconProps) => (
  <Icon {...p}><circle cx="12" cy="12" r="3" /><path d="M4 8V6a2 2 0 0 1 2-2h2M4 16v2a2 2 0 0 0 2 2h2M16 4h2a2 2 0 0 1 2 2v2M16 20h2a2 2 0 0 0 2-2v-2" /></Icon>
)
export const MoveIcon = (p: IconProps) => (
  <Icon {...p}><path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3" /></Icon>
)
export const PlayIcon = (p: IconProps) => <Icon {...p}><path d="M8 5l11 7-11 7z" fill="currentColor" stroke="none" /></Icon>
