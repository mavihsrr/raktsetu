import { useState } from 'react'
import { AlertTriangle, ArrowUpRight, Check, Copy, MapPin } from 'lucide-react'
import { directionsUrl, planText } from '../lib/planText'
import type { RequestState } from '../types'
import { RouteBadge, km } from './bits'

/** The answer the coordinator walks away with: who to collect from, in what order, and what to do next. */
export function PlanView({ st, demo }: { st: RequestState; demo: boolean }) {
  const p = st.plan
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(planText(st))
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch { /* clipboard blocked: the plan is still on screen */ }
  }

  return (
    <div className={`block plan ${p.short_by ? 'plan-short' : ''}`}>
      <div className="block-head">
        <h3 className="block-title">Plan</h3>
        <span className={`plan-state ${p.short_by ? 'is-short' : 'is-met'}`}>{p.short_by ? `Short by ${p.short_by}` : 'Target met'}</span>
        <button className="btn btn-ghost plan-copy" onClick={copy} aria-live="polite">
          {copied ? <><Check size={14} aria-hidden /> Copied</> : <><Copy size={14} aria-hidden /> Copy plan</>}
        </button>
      </div>

      {demo && (
        <p className="banner banner-amber"><AlertTriangle size={14} aria-hidden /> The demo line answered for these banks. Phone each bank to verify before sending the sample.</p>
      )}

      {p.allocation.length ? (
        <ol className="alloc-cards">
          {p.allocation.map((a, i) => {
            const dir = directionsUrl(a.lat, a.lng)
            return (
              <li key={a.bank_id ?? i} className="alloc-card">
                <span className="alloc-rank num">{i + 1}</span>
                <div className="alloc-body">
                  <span className="alloc-name">{a.bank_name} <RouteBadge route={a.route} mode={a.mode} /></span>
                  <span className="alloc-meta num">
                    <b>{a.units} × {a.group}</b>{a.exact_match ? '' : ' (compatible)'}
                    {' · '}{a.eta_min != null ? `~${a.eta_min} min away` : km(a.distance_km)}
                    {a.hold_hours ? ` · held ${a.hold_hours} h` : ''}
                  </span>
                </div>
                {dir && (
                  <a className="btn btn-ghost alloc-dir" href={dir} target="_blank" rel="noreferrer" aria-label={`Directions to ${a.bank_name}`}>
                    <MapPin size={14} aria-hidden /> Directions
                  </a>
                )}
              </li>
            )
          })}
        </ol>
      ) : (
        <p className="muted small">No bank has confirmed units yet.</p>
      )}

      {p.late_vs_deadline.length > 0 && (
        <p className="banner banner-amber"><AlertTriangle size={14} aria-hidden /> May miss the deadline: {p.late_vs_deadline.join(', ')}</p>
      )}

      {p.steps.length > 0 && (
        <>
          <p className="wave-label">Next steps</p>
          <ol className="plan-steps">{p.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
        </>
      )}

      {p.backups.length > 0 && (
        <>
          <p className="wave-label">Backup stock, if a bank falls through</p>
          <ul className="leads">
            {p.backups.map((b, i) => (
              <li key={i}><span>{b.bank_name} · <span className="num">{b.units} × {b.group} · {km(b.distance_km)}</span></span></li>
            ))}
          </ul>
        </>
      )}

      {p.leads.length > 0 && (
        <>
          <p className="wave-label">Unverified leads, call yourself</p>
          <ul className="leads">
            {p.leads.map((l, i) => (
              <li key={i}>
                <span>{l.bank_name} · <span className="num">{km(l.distance_km)}</span></span>
                {l.phone && <a href={`tel:${l.phone.split(',')[0].trim()}`} className="mono">{l.phone.split(',')[0].trim()} <ArrowUpRight size={12} aria-hidden /></a>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
