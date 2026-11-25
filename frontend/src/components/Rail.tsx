import type { ReactNode } from 'react'
import { PanelLeftOpen, PanelRightOpen } from 'lucide-react'

interface Props {
  side: 'left' | 'right'
  label: string
  shortcut: string
  onOpen: () => void
  /** Compact facts that stay visible while the panel is collapsed. */
  children?: ReactNode
}

/** A collapsed sidebar: a slim, clickable rail that keeps the essentials in view. */
export function Rail({ side, label, shortcut, onOpen, children }: Props) {
  const Icon = side === 'left' ? PanelLeftOpen : PanelRightOpen
  return (
    <button className={`rail rail-${side}`} onClick={onOpen} aria-label={`Show ${label} (${shortcut})`} title={`Show ${label}  ${shortcut}`}>
      <Icon size={17} className="rail-icon" aria-hidden />
      <span className="rail-body">{children}</span>
      <span className="rail-label">{label}</span>
    </button>
  )
}

export function CollapseButton({ side, label, shortcut, onClick }: { side: 'left' | 'right'; label: string; shortcut: string; onClick: () => void }) {
  return (
    <button className="btn btn-icon btn-ghost collapse-btn" onClick={onClick} aria-label={`Hide ${label} (${shortcut})`} title={`Hide ${label}  ${shortcut}`}>
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d={side === 'left' ? 'M9 3v18M16 15l-3-3 3-3' : 'M15 3v18M8 9l3 3-3 3'} />
      </svg>
    </button>
  )
}
