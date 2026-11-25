import { callRoute } from '../lib/route'
import type { Flags } from '../types'
import type { StreamHealth } from '../hooks/useLive'

export function TopBar({ flags, flagsError, health }: { flags: Flags | null; flagsError: boolean; health: StreamHealth }) {
  const v = flags?.values
  const f = flags
  const route = callRoute(flags)
  return (
    <header className="topbar">
      <div className="brand">
        <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden><defs><linearGradient id="brand-grad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffa6e0" /><stop offset="0.5" stopColor="#8b9dff" /><stop offset="1" stopColor="#3b4bd8" /></linearGradient></defs><path d="M16 4c-4.6 6.3-8 11-8 15a8 8 0 0 0 16 0c0-4-3.4-8.7-8-15z" fill="url(#brand-grad)" /></svg>
        <span className="brand-name">RaktSetu</span>
        <span className="brand-sub">Voice blood finder</span>
      </div>
      <ul className="chips" aria-label="System status">
        <li className={`chip ${health === 'live' ? 'chip-ok' : 'chip-warn'}`}>{health === 'live' ? 'Updates live' : 'Reconnecting…'}</li>
        {flagsError && <li className="chip chip-bad">Flags unavailable</li>}
        {v && (
          <>
            <li className={`chip ${v.outbound_calls_enabled ? '' : 'chip-bad'}`}>{v.outbound_calls_enabled ? 'Outbound on' : 'Outbound killed'}</li>
            {/* where "start calling" really rings, mirroring the backend's routing */}
            {route === 'real' && <li className="chip chip-live" title="Real bank numbers from e-RaktKosh will be dialled">Calling real banks</li>}
            {route === 'demo' && <li className="chip chip-demo" title="A demo phone answers for each bank; real banks are never dialled">Demo line · real banks off</li>}
            {route === 'none' && <li className="chip" title="Nobody is phoned; banks are listed as leads with their numbers">Leads only · no calls</li>}
            <li className="chip" title="Donor recall is for restock and never counts toward the patient">
              {v.call_donors === false ? 'Donor calls off' : (f?.demo_lines?.donors ?? 0) > 0 && route !== 'none' ? 'Donors: demo line' : 'Donors: simulated'}
            </li>
            <li className={`chip ${v.autopilot_mode ? 'chip-warn' : ''}`}>Autopilot {v.autopilot_mode ? 'on' : 'off'}</li>
          </>
        )}
      </ul>
    </header>
  )
}
