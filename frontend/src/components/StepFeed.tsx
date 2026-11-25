import { AlertCircle, Check, Loader2, Phone, Wrench } from 'lucide-react'
import { isRunning, payloadOf } from '../lib/progress'
import type { BackendEvent } from '../types'
import { clock } from './bits'

const CALL_TYPES = new Set(['call_started', 'bank_result', 'bank_confirmed', 'donor_result', 'calls_started', 'approval_needed'])

/** What the backend is doing right now, step by step (tool calls, e-RaktKosh, distances, phone calls). */
export function StepFeed({ events, limit = 10 }: { events: BackendEvent[]; limit?: number }) {
  const rows = events.map((e, i) => ({ e, i })).filter(({ e }) => (e.type === 'progress' || CALL_TYPES.has(e.type)) && e.say)
  const shown = rows.slice(-limit).reverse()
  if (!shown.length) return null
  return (
    <ul className="steps-feed" aria-live="polite">
      {shown.map(({ e, i }) => {
        const p = payloadOf(e)
        const running = e.type === 'progress' && isRunning(events, i)
        const icon = running ? <Loader2 size={14} className="spin" aria-hidden />
          : p.phase === 'error' ? <AlertCircle size={14} aria-hidden />
          : p.stage === 'tool' ? <Wrench size={14} aria-hidden />
          : e.type !== 'progress' ? <Phone size={14} aria-hidden />
          : <Check size={14} aria-hidden />
        return (
          <li key={e.seq} className={`step ${running ? 'is-running' : ''} ${p.phase === 'error' ? 'is-error' : ''}`}>
            <span className="step-icon">{icon}</span>
            <span className="step-text">{e.say}</span>
            <time className="step-time num">{clock(e.ts)}</time>
          </li>
        )
      })}
    </ul>
  )
}
