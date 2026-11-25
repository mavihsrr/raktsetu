import { useEffect, useState } from 'react'
import type { RequestStatus, Route } from '../types'

export const COMPONENT_LABEL: Record<string, string> = {
  packed_red_cells: 'packed red cells',
  whole_blood: 'whole blood',
  platelets: 'platelets',
}

const STATUS_LABEL: Record<RequestStatus, string> = {
  planned: 'Leads found',
  calling: 'Calling',
  awaiting_wave2: 'Needs approval',
  resolved: 'Resolved',
  unresolved: 'Short',
  cancelled: 'Cancelled',
}

export function StatusPill({ status }: { status: RequestStatus }) {
  return <span className={`pill pill-${status}`}>{STATUS_LABEL[status] ?? status}</span>
}

/** Who actually got phoned. DEMO LINE must never read as a real bank call. */
export function RouteBadge({ route, mode, donor = false }: { route?: Route; mode?: string | null; donor?: boolean }) {
  if (route === 'demo') return <span className="badge badge-demo" title={donor ? 'A demo phone stood in for a donor; no real donor was phoned' : 'A demo phone stood in for this bank; the bank itself was not phoned'}>Demo line</span>
  if (route === 'real') return <span className="badge badge-live" title="The bank's real number was dialled">Live</span>
  if (route === 'lead') return <span className="badge badge-lead" title="Not phoned; call this bank yourself">Lead</span>
  if (mode === 'live') return <span className="badge badge-live">Live</span>
  if (mode) return <span className="badge" title="Simulated call">Sim</span>
  return null
}

export function km(d: number | null | undefined): string {
  return d == null ? 'distance unknown' : `${d < 10 ? d.toFixed(1) : Math.round(d)} km`
}

export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

export function Countdown({ deadline }: { deadline?: number | null }) {
  const now = useNow()
  if (!deadline) return <span className="countdown muted">No deadline</span>
  const s = Math.round(deadline - now / 1000)
  if (s <= 0) return <span className="countdown late">Deadline passed</span>
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const urgent = s < 45 * 60
  return (
    <span className={`countdown num ${urgent ? 'late' : ''}`} title="Time left to the deadline">
      {h > 0 ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(sec).padStart(2, '0')}s`} left
    </span>
  )
}

export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
