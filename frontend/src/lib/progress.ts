import type { BackendEvent, PortalBank } from '../types'

export type Stage = 'tool' | 'geocode' | 'portal' | 'distance' | string

export interface StepPayload {
  stage?: Stage
  phase?: 'start' | 'done' | 'error' | 'update'
  tool?: string
  banks?: PortalBank[]
  total?: number
  located?: number
}

export function payloadOf(e: BackendEvent): StepPayload {
  if (typeof e.payload !== 'string') return (e.payload ?? {}) as StepPayload
  try { return JSON.parse(e.payload) } catch { return {} }
}

/** Is this step still running? A "start" with no later "done"/"error" for the same stage. */
export function isRunning(events: BackendEvent[], i: number): boolean {
  const p = payloadOf(events[i])
  if (p.phase !== 'start' || p.stage === 'tool') return false
  return !events.slice(i + 1).some((e) => {
    const q = payloadOf(e)
    return q.stage === p.stage && (q.phase === 'done' || q.phase === 'error')
  })
}
