import { useState } from 'react'
import { AlertCircle, AlertTriangle, ArrowUpRight, Plus, Radar } from 'lucide-react'
import { api } from '../lib/api'
import { callRoute, type CallRoute } from '../lib/route'
import { payloadOf } from '../lib/progress'
import type { BackendEvent, Call, Flags, RequestRow, RequestState } from '../types'
import { COMPONENT_LABEL, Countdown, RouteBadge, StatusPill, km } from './bits'
import { BanksList } from './BanksList'
import { CallRow } from './CallRow'
import { StepFeed } from './StepFeed'
import { RequestForm } from './RequestForm'
import { CollapseButton, Rail } from './Rail'

interface Props {
  list: RequestRow[]
  selected: string | null
  onSelect: (id: string) => void
  state: RequestState | null
  onChanged: () => void
  loadError: string | null
  open: boolean
  onToggle: () => void
  flags: Flags | null
  /** search steps of a request that has no row yet (tool call, map, e-RaktKosh, distances) */
  progress: BackendEvent[]
}

export function LiveStatus({ list, selected, onSelect, state, onChanged, loadError, open, onToggle, flags, progress }: Props) {
  const [creating, setCreating] = useState(false)
  const searching = progress.length > 0
  const showForm = !searching && (creating || (!state && list.length === 0))
  const portalBanks = [...progress].reverse().map((e) => payloadOf(e).banks).find(Boolean)

  if (!open) {
    const r = state?.request
    const p = state?.plan
    const onCall = state?.calls.filter((c) => c.status === 'dialing').length ?? 0
    const attention = r?.status === 'planned' || r?.status === 'awaiting_wave2'
    return (
      <section className="col col-status is-collapsed" aria-label="Live status (collapsed)">
        <Rail side="right" label="Live status" shortcut="]" onOpen={onToggle}>
          {attention && <AlertCircle size={16} className="rail-alert" aria-label="Needs your approval" />}
          {r && p && (
            <span className={`rail-units num rail-${r.status}`}>
              <b>{Math.min(p.confirmed, p.needed)}</b>
              <i>/{p.needed}</i>
            </span>
          )}
          {onCall > 0 && <span className="rail-live num" title={`${onCall} on call`}><span className="dialing" />{onCall}</span>}
        </Rail>
      </section>
    )
  }

  return (
    <section className="col col-status" aria-label="Live status">
      <header className="col-head">
        <h2>Live status</h2>
        <div className="head-actions">
          {list.length > 0 && (
            <select className="req-select" value={selected ?? ''} onChange={(e) => { setCreating(false); onSelect(e.target.value) }} aria-label="Request">
              {list.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.units}× {r.blood_group} · {r.hospital_name}
                </option>
              ))}
            </select>
          )}
          <button className="btn btn-icon" onClick={() => setCreating(true)} title="Type a new request" aria-label="Type a new request">
            <Plus size={16} />
          </button>
          <CollapseButton side="right" label="live status" shortcut="]" onClick={onToggle} />
        </div>
      </header>

      <div className="col-scroll">
        {loadError && <p className="banner banner-red" role="alert">{loadError}</p>}
        {searching && (
          <>
            <div className="block">
              <div className="block-head"><h3 className="block-title">Live search</h3><span className="counts">happening now</span></div>
              <StepFeed events={progress} limit={8} />
            </div>
            <BanksList portal={portalBanks} locating />
          </>
        )}
        {showForm ? (
          <div className="block">
            <h3 className="block-title">Type a request</h3>
            <p className="muted small">Or just say it to the agent. Banks and live stock come from e-RaktKosh.</p>
            <RequestForm
              onCreated={(id) => { setCreating(false); onSelect(id); onChanged() }}
              onCancel={list.length ? () => setCreating(false) : undefined}
            />
          </div>
        ) : state && !searching ? (
          <RequestView st={state} onChanged={onChanged} route={callRoute(flags)} />
        ) : searching ? null : (
          <p className="empty">Loading…</p>
        )}
      </div>
    </section>
  )
}

function RequestView({ st, onChanged, route }: { st: RequestState; onChanged: () => void; route: CallRoute }) {
  const r = st.request
  const p = st.plan
  const [busy, setBusy] = useState(false)
  const banks = st.calls.filter((c) => c.target_type === 'bank')
  const donors = st.calls.filter((c) => c.target_type === 'donor')
  const leadsEvent = [...st.events].reverse().find((e) => e.type === 'leads_found')
  const leadsPayload = (typeof leadsEvent?.payload === 'string' ? safeJson(leadsEvent.payload) : leadsEvent?.payload) as
    | {
        shortlist?: { id: string; portal_stale?: boolean }[]
        other_banks?: { id: string; portal_stale?: boolean }[]
        banks_in_district?: number
        district?: string
        banks_with_stock?: number
        approx_location?: boolean
      }
    | undefined
  // portal_stale lives on the leads payload, not on call rows: match by bank id
  const stale = new Set(
    [...(leadsPayload?.shortlist ?? []), ...(leadsPayload?.other_banks ?? [])].filter((b) => b.portal_stale).map((b) => b.id),
  )
  const approvalSay = [...st.events].reverse().find((e) => e.type === 'approval_needed')?.say

  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    try { await fn() } finally { setBusy(false); onChanged() }
  }

  const live = banks.filter((c) => c.status === 'dialing').length
  const confirmedBanks = banks.filter((c) => c.status === 'completed' && c.confirmed_units > 0).length
  const queued = banks.filter((c) => c.status === 'queued').length
  const nonePhoned = banks.length > 0 && banks.every((c) => c.route === 'lead')
  // units "confirmed" by the demo phone are not the bank's word: never present them as such
  const demoConfirmed = p.allocation.some((a) => a.route === 'demo')
  const nShort = leadsPayload?.shortlist?.length ?? 0
  const startQ =
    route === 'real' ? `Phone the ${nShort} shortlisted banks now?`
    : route === 'demo' ? `Ring the demo line for the ${nShort} shortlisted banks?`
    : `List the ${nShort} shortlisted banks as leads? No one will be phoned.`
  const startBtn = route === 'real' ? 'Yes, call the banks' : route === 'demo' ? 'Yes, ring the demo line' : 'List the leads'
  const donorDemo = donors.some((c) => c.route === 'demo')

  return (
    <>
      <div className="block summary">
        <div className="summary-top">
          <h3 className="req-title">
            <span className="num">{r.units}</span>× {r.blood_group} <span className="muted">{p.component_label || COMPONENT_LABEL[r.component]}</span>
          </h3>
          <StatusPill status={r.status} />
        </div>
        <p className="summary-meta">
          {st.hospital.name} · <Countdown deadline={r.deadline_at} />
          {r.wave > 0 && <> · wave {r.wave}, {r.bank_radius_km} km{r.wave >= 2 && r.wave2_radius_km ? ` → ${r.wave2_radius_km} km` : ''}</>}
        </p>

        <div className="units-row" aria-label={`${p.confirmed} of ${p.needed} units phone-confirmed`}>
          <span className="units-big num">{Math.min(p.confirmed, p.needed)}<span className="muted"> / {p.needed}</span></span>
          <span className="units-label">{nonePhoned ? 'no bank phoned yet' : demoConfirmed ? 'units confirmed on the demo line, not by the bank' : 'units confirmed on the phone'}</span>
        </div>
        <div className="segments" aria-hidden>
          {Array.from({ length: p.needed }, (_, i) => <i key={i} className={i < p.confirmed ? 'on' : ''} />)}
        </div>
        <p className="fine">Portal stock is only a lead. Donors restock the bank and never count here.</p>
      </div>

      <div className="block">
        <div className="block-head"><h3 className="block-title">Live activity</h3><span className="counts">newest first</span></div>
        <StepFeed events={st.events} limit={8} />
      </div>

      {r.status === 'planned' && (
        <div className="gate gate-blue">
          <p className="gate-q">{startQ}</p>
          {leadsPayload?.banks_in_district != null && (
            <p className="gate-sub">
              {leadsPayload.banks_in_district} banks in {leadsPayload.district} district
              {leadsPayload.banks_with_stock != null ? `, ${leadsPayload.banks_with_stock} listing compatible stock` : ''}.
              {route === 'demo' ? ' Real bank calls are off; a demo phone answers for each bank.' : route === 'real' ? ' Portal stock is checked by phone.' : ''}
              {leadsPayload.approx_location ? ' Distances are from the city centre.' : ''}
            </p>
          )}
          <div className="gate-actions">
            <button className="btn btn-ghost" disabled={busy} onClick={() => act(() => api.cancel(r.id))}>Cancel</button>
            <button className="btn btn-primary" disabled={busy} onClick={() => act(() => api.start(r.id))}>{startBtn}</button>
          </div>
        </div>
      )}
      {r.status === 'awaiting_wave2' && (
        <div className="gate gate-amber">
          {nonePhoned ? (
            <>
              <p className="gate-q"><Radar size={15} aria-hidden /> Real bank calls are off, so no bank was phoned.</p>
              <p className="gate-sub">Approving lists the next banks as leads with their numbers, for you to call.</p>
            </>
          ) : (
            <p><Radar size={15} aria-hidden /> {approvalSay || 'Still short. Widen the search to the next banks?'}</p>
          )}
          <div className="gate-actions">
            <button className="btn btn-ghost" disabled={busy} onClick={() => act(() => api.cancel(r.id))}>Stop here</button>
            <button className="btn btn-primary" disabled={busy} onClick={() => act(() => api.approve(r.id))}>
              {nonePhoned ? 'List the next banks' : 'Approve wave 2'}
            </button>
          </div>
        </div>
      )}

      {(r.status === 'resolved' || r.status === 'unresolved') && <PlanBlock st={st} demo={demoConfirmed} />}

      <div className="block">
        <div className="block-head">
          <h3 className="block-title">Bank calls</h3>
          <span className="counts num">
            {live > 0 && <span className="c-blue">{live} on call</span>}
            {confirmedBanks > 0 && <span className="c-green">{confirmedBanks} confirmed</span>}
            {queued > 0 && <span>{queued} queued</span>}
          </span>
          {r.status === 'calling' && (
            <button className="btn btn-danger-quiet" disabled={busy} onClick={() => { if (confirm('Cancel this request? Queued calls will be skipped.')) act(() => api.cancel(r.id)) }}>
              Cancel request
            </button>
          )}
        </div>
        {banks.length ? (
          <WaveList calls={banks} stale={stale} />
        ) : (
          <Shortlist st={st} />
        )}
      </div>

      <BanksList banks={st.banks} group={r.blood_group} locating={(st.banks ?? []).some((b) => b.distance_km == null)} />

      <div className="block">
        <div className="block-head">
          <h3 className="block-title">Donors</h3>
          <span className="counts">restock only, not counted</span>
          {donorDemo && <span className="badge badge-demo" title="A demo phone stands in for a registered donor">Demo donor line</span>}
        </div>
        {donors.length ? (
          <ul className="calls">{donors.map((c) => <CallRow key={c.id} c={c} />)}</ul>
        ) : (
          <p className="muted small">No donor recall calls yet.</p>
        )}
      </div>
    </>
  )
}

function WaveList({ calls, stale }: { calls: Call[]; stale: Set<string> }) {
  const waves = [...new Set(calls.map((c) => c.wave))].sort()
  return (
    <>
      {waves.map((w) => (
        <div key={w}>
          {waves.length > 1 && <p className="wave-label">Wave {w}</p>}
          <ul className="calls">{calls.filter((c) => c.wave === w).map((c) => <CallRow key={c.id} c={c} stale={stale.has(c.target_id)} />)}</ul>
        </div>
      ))}
    </>
  )
}

function Shortlist({ st }: { st: RequestState }) {
  const ev = [...st.events].reverse().find((e) => e.type === 'leads_found')
  const payload = (typeof ev?.payload === 'string' ? safeJson(ev.payload) : ev?.payload) as
    | { shortlist?: { id: string; name: string; distance_km: number | null; portal_units: number; portal_stale?: boolean }[]; banks_in_district?: number; district?: string }
    | undefined
  if (!payload?.shortlist?.length) return <p className="muted small">No calls yet.</p>
  return (
    <>
      <p className="muted small">
        {payload.banks_in_district} banks in {payload.district} district from e-RaktKosh. Shortlist to phone:
      </p>
      <ul className="calls">
        {payload.shortlist.map((b) => (
          <li key={b.id} className="call">
            <div className="call-main static">
              <span className="call-icon" />
              <span className="call-body">
                <span className="call-name">{b.name}</span>
                <span className="call-meta">
                  <span className="num">{km(b.distance_km)}</span>
                  {b.portal_stale && <span className="tag tag-amber">portal stock over 7 days old</span>}
                </span>
              </span>
              <span className="call-result units-text">portal <span className="num">{b.portal_units}</span></span>
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}

function PlanBlock({ st, demo }: { st: RequestState; demo: boolean }) {
  const p = st.plan
  return (
    <div className={`block plan ${p.short_by ? 'plan-short' : ''}`}>
      <div className="block-head">
        <h3 className="block-title">Plan</h3>
        <span className="counts">{p.short_by ? `short by ${p.short_by}` : 'target met'}</span>
      </div>
      {demo && (
        <p className="banner banner-amber"><AlertTriangle size={14} aria-hidden /> The demo line answered for these banks. Phone each bank to verify before sending the sample.</p>
      )}
      {p.allocation.length ? (
        <ol className="alloc">
          {p.allocation.map((a, i) => (
            <li key={i}>
              <span className="alloc-name">{a.bank_name} <RouteBadge route={a.route} mode={a.mode} /></span>
              <span className="alloc-meta num">
                {a.units} × {a.group}{a.exact_match ? '' : ' (compatible)'} · {a.eta_min != null ? `~${a.eta_min} min` : km(a.distance_km)}
                {a.hold_hours ? ` · hold ${a.hold_hours} h` : ''}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted small">No bank has confirmed units yet.</p>
      )}
      <ul className="steps">{p.steps.map((s, i) => <li key={i}>{s}</li>)}</ul>
      {p.late_vs_deadline.length > 0 && (
        <p className="banner banner-amber"><AlertTriangle size={14} aria-hidden /> May miss the deadline: {p.late_vs_deadline.join(', ')}</p>
      )}
      {p.leads.length > 0 && (
        <>
          <p className="wave-label">Unverified leads, call yourself</p>
          <ul className="leads">
            {p.leads.map((l, i) => (
              <li key={i}>
                <span>{l.bank_name} · <span className="num">{km(l.distance_km)}</span></span>
                {l.phone && <a href={`tel:${l.phone}`} className="mono">{l.phone} <ArrowUpRight size={12} aria-hidden /></a>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function safeJson(s: string): unknown {
  try { return JSON.parse(s) } catch { return undefined }
}
