import { useLayoutEffect, useRef } from 'react'

/**
 * FLIP for a list: rows marked `data-flip="<id>"` glide from their previous position to the new one
 * whenever the order changes. Uses the Web Animations API (transform only) and does nothing under reduced motion.
 * The list element needs `position: relative`.
 */
export function useFlip<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const prev = useRef(new Map<string, number>())

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const next = new Map<string, number>()
    el.querySelectorAll<HTMLElement>('[data-flip]').forEach((n) => {
      const id = n.dataset.flip!
      const top = n.offsetTop
      next.set(id, top)
      const was = prev.current.get(id)
      if (!reduce && was != null && Math.abs(was - top) > 1) {
        n.animate([{ transform: `translateY(${was - top}px)` }, { transform: 'none' }], {
          duration: 460,
          easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
        })
      }
    })
    prev.current = next
  })
  return ref
}
