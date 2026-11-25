import { useState } from 'react'
import { Check, ChevronDown, Clock, Minus, PhoneOff, SkipForward } from 'lucide-react'
import type { Call } from '../types'
import { RouteBadge, km, useNow } from './bits'

function StatusIcon({ c }: { c: Call }) {
  if (c.status === 'dialing') return <span className="dialing" role="img" aria-label="Dialing" />
  if (c.status === 'completed') {
    const ok = c.target_type === 'bank' ? c.confirmed_units + c.alt_units > 0 : c.willing === 'yes'
    return ok ? <Check size={15} className="ic-green" aria-label="Confirmed" /> : <Minus size={15} className="ic-muted" aria-label="None available" />
  }
  if (c.status === 'queued') return <Clock size={14} className="ic-muted" aria-label="Queued" />
  if (c.status === 'skipped') return <SkipForward size={14} className="ic-muted" aria-label="Skipped" />
  return <PhoneOff size={14} className="ic-red" aria-label={c.status.replace('_', ' ')} />
}

const STATUS_TEXT: Record<string, string> = {
  queued: 'Queued', dialing: 'Calling…', completed: 'Done', no_answer: 'No answer',
  busy: 'Busy', failed: 'Failed', skipped: 'Skipped',
}

const WILLING: Record<string, string> = { yes: 'Will donate (restock)', later: 'Maybe later', no: 'Declined' }

/** m:ss since the call was placed, ticking while the phone rings. */
function RingTimer({ since }: { since?: number | null }) {
  const now = useNow(1000)
  if (!since) return <span className="ring-timer num">calling…</span>
  const s = Math.max(0, Math.round(now / 1000 - since))
  return <span className="ring-timer num" aria-label={`ringing for ${s} seconds`}>{Math.floor(s / 60)}:{String(s % 60).padStart(2, '0')}</span>
}

export function CallRow({ c, stale = false }: { c: Call; stale?: boolean }) {
  const [open, setOpen] = useState(false)
  const bank = c.target_type === 'bank'
  const done = c.status === 'completed'
  const demo = c.route === 'demo'
  // portal vs phone only means something when the bank itself answered
  const mismatch = bank && !demo && done && c.portal_units != null && c.portal_units !== c.confirmed_units
  const hasDetail = (c.transcript && c.transcript.length > 0) || !!c.notes || (c.route === 'lead' && !!c.phone)

  let result: React.ReactNode
  if (bank && done) {
    result = (
      <span className="units num">
        {c.confirmed_units}
        {c.alt_units > 0 && <small> +{c.alt_units} {c.alt_group}</small>}
        <small> {c.confirmed_units === 1 ? 'unit' : 'units'}</small>
      </span>
    )
  } else if (!bank && done) {
    result = <span className={`units-text ${c.willing === 'yes' ? 'c-green' : ''}`}>{WILLING[c.willing ?? 'no'] ?? 'Declined'}</span>
  } else if (c.route === 'lead') {
    result = <span className="units-text">Call yourself</span>
  } else {
    result = c.status === 'dialing'
      ? <span className="units-text st-dialing"><RingTimer since={c.started_at} /></span>
      : <span className={`units-text st-${c.status}`}>{STATUS_TEXT[c.status] ?? c.status}</span>
  }

  return (
    <li data-flip={c.id} className={`call ${c.status === 'dialing' ? 'is-dialing' : ''} ${done && bank && c.confirmed_units > 0 ? 'is-confirmed' : ''}`}>
      <button className="call-main" onClick={() => hasDetail && setOpen(!open)} aria-expanded={hasDetail ? open : undefined} disabled={!hasDetail}>
        <span className="call-icon"><StatusIcon c={c} /></span>
        <span className="call-body">
          <span className="call-name">
            {c.target_name} <RouteBadge route={c.route} mode={c.mode} donor={!bank} />
          </span>
          <span className="call-meta">
            <span className="num">{!bank && demo && c.distance_km == null ? 'demo line' : km(c.distance_km)}</span>
            {bank && c.portal_units != null && <span>portal <span className="num">{c.portal_units}</span></span>}
            {stale && <span className="tag tag-amber">portal stock over 7 days old</span>}
            {bank && demo && done && <span className="tag tag-violet">demo line answered, not the bank</span>}
            {mismatch && <span className="tag tag-amber">portal {c.portal_units} ≠ phone {c.confirmed_units}</span>}
            {c.hold_hours ? <span>hold <span className="num">{c.hold_hours} h</span></span> : null}
          </span>
        </span>
        <span className="call-result">{result}</span>
        {hasDetail && <ChevronDown size={15} className={`chev ${open ? 'open' : ''}`} aria-hidden />}
      </button>
      {open && (
        <div className="call-detail">
          {c.route === 'lead' && c.phone && <p>Bank phone (e-RaktKosh): <a href={`tel:${c.phone}`} className="mono">{c.phone}</a></p>}
          {demo && <p className="muted">{bank
            ? 'This call went to the demo line, not the bank. The agent named the bank, but phone the bank to verify.'
            : 'Demo donor line: no real donor was phoned.'}</p>}
          {c.notes && <p className="muted">{c.notes}</p>}
          {c.transcript?.map((t, i) => (
            <p key={i} className={`tline ${t.role === 'agent' || t.role === 'bot' ? 'tline-agent' : ''}`}>
              <b>{t.role === 'bot' ? 'agent' : t.role}</b> {t.text}
            </p>
          ))}
        </div>
      )}
    </li>
  )
}
