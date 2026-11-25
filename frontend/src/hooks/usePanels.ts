import { useCallback, useEffect, useState } from 'react'

type Side = 'left' | 'right'
const KEY = 'raktsetu.panels'

function load(): Record<Side, boolean> {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    return { left: v.left !== false, right: v.right !== false }
  } catch {
    return { left: true, right: true }
  }
}

/** Which sidebars are open. Remembered per browser; `[` and `]` toggle them. */
export function usePanels() {
  const [open, setOpen] = useState(load)

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(open)) } catch { /* private mode */ }
  }, [open])

  const toggle = useCallback((side: Side, value?: boolean) => {
    setOpen((o) => ({ ...o, [side]: value ?? !o[side] }))
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (t instanceof Element && t.closest('input, textarea, select, [contenteditable]')) return
      if (e.key === '[') toggle('left')
      else if (e.key === ']') toggle('right')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle])

  return { open, toggle }
}
