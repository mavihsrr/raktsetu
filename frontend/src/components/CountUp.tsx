import { useEffect, useRef, useState } from 'react'

/** A number that counts to its new value instead of jumping. Instant under reduced motion. */
export function CountUp({ value, ms = 520 }: { value: number; ms?: number }) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)

  useEffect(() => {
    if (from.current === value) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { from.current = value; setShown(value); return }
    const start = performance.now()
    const a = from.current
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms)
      const e = 1 - Math.pow(1 - t, 3) // ease-out
      setShown(Math.round(a + (value - a) * e))
      if (t < 1) raf = requestAnimationFrame(tick)
      else from.current = value
    }
    raf = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf); from.current = value }
  }, [value, ms])

  return <>{shown}</>
}
