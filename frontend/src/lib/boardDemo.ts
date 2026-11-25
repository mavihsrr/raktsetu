import { useEffect, useState } from 'react'
import type { Call, RequestState } from '../types'

/**
 * Dev-only (`npm run dev`, open /#boarddemo): a looping synthetic request so the call board, radar,
 * units counter and conversation can be tuned without placing a single call. Never used in production:
 * App only calls this when import.meta.env.DEV is true, and the bundler drops it from the build.
 */
const HOSP = { lat: 15.3647, lng: 75.124 }
const BANKS = [
  { id: 'D1', name: 'KLE Hospital & MRC Blood Centre', km: 1.2, dlat: 0.004, dlng: 0.006, portal: 12 },
  { id: 'D2', name: 'District Hospital Blood Centre', km: 3.4, dlat: -0.02, dlng: 0.012, portal: 5 },
  { id: 'D3', name: 'Rotary Blood Bank', km: 4.9, dlat: 0.03, dlng: -0.018, portal: 0 },
  { id: 'D4', name: 'Karnataka Medical College Blood Centre', km: 6.1, dlat: -0.03, dlng: -0.035, portal: 103 },
  { id: 'D5', name: 'Sdm College Blood Centre', km: 7.7, dlat: 0.012, dlng: 0.05, portal: 11 },
]

// seconds into the loop at which each bank is placed, and how it ends
const PLAN: { at: number; ends: number; units: number; status: 'completed' | 'no_answer' }[] = [
  { at: 2, ends: 9, units: 1, status: 'completed' },
  { at: 2, ends: 13, units: 0, status: 'no_answer' },
  { at: 5, ends: 17, units: 2, status: 'completed' },
  { at: 9, ends: 99, units: 0, status: 'completed' },
  { at: 13, ends: 99, units: 0, status: 'completed' },
]
const LOOP = 24

function build(t: number, base: number): RequestState {
  const calls: Call[] = BANKS.map((b, i) => {
    const p = PLAN[i]
    const placed = t >= p.at
    const done = t >= p.ends
    const status = !placed ? 'queued' : done ? p.status : 'dialing'
    return {
      id: `c${i}`, target_id: b.id, target_type: 'bank', target_name: b.name, status, route: 'demo', mode: 'live', wave: 1,
      distance_km: b.km, portal_units: b.portal, confirmed_units: done && p.status === 'completed' ? p.units : 0, alt_units: 0,
      hold_hours: done && p.units > 0 ? 6 : null, lat: HOSP.lat + b.dlat, lng: HOSP.lng + b.dlng,
      started_at: placed ? base + p.at : null,
    } as Call
  })
  const confirmed = calls.reduce((a, c) => a + c.confirmed_units, 0)
  const status = t < 2 ? 'planned' : t < 20 ? 'calling' : 'resolved'
  return {
    request: { id: 'DEMO', blood_group: 'B+', units: 3, component: 'packed_red_cells', status, hospital_name: 'KIMS Hospital Hubli',
      confirmed_units: confirmed, created_at: base, deadline_at: base + 3 * 3600, wave: 1, bank_radius_km: 8 },
    hospital: { name: 'KIMS Hospital Hubli', ...HOSP },
    calls, counts: {}, needs_approval: false, done: status === 'resolved',
    events: [
      'Searching for blood banks near KIMS Hospital Hubli…',
      'Found Dharwad district. Fetching e-RaktKosh stock…',
      'e-RaktKosh lists 11 blood banks in Dharwad; 9 show compatible stock.',
      'Mapped 5 banks; calculating distances…',
      'Shortlisted 5 banks within 8 km.',
    ].map((say, i) => ({ seq: i + 1, request_id: 'DEMO', ts: base - 20 + i * 2, type: 'progress', payload: '{}', say })),
    plan: { needed: 3, confirmed, short_by: Math.max(0, 3 - confirmed), group: 'B+', component_label: 'packed red cells',
      allocation: calls.filter((c) => c.status === 'completed' && c.confirmed_units > 0).map((c) => ({
        bank_id: c.target_id, bank_name: c.target_name, units: c.confirmed_units, group: 'B+', exact_match: true,
        distance_km: c.distance_km, eta_min: Math.round((c.distance_km ?? 0) * 3.2 + 4), hold_hours: 6, route: 'demo', mode: 'live', lat: c.lat, lng: c.lng })),
      backups: status === 'resolved' ? [{ bank_name: BANKS[3].name, units: 4, group: 'B+', exact_match: true, distance_km: BANKS[3].km }] : [],
      leads: [],
      steps: [
        'Send the patient sample and requisition to ' + BANKS[0].name + ' for crossmatch.',
        'Ask each bank to hold the units until crossmatch completes; hold times are listed.',
        'Final compatibility is decided only by the crossmatch at the issuing bank.',
      ],
      late_vs_deadline: [], deadline_minutes_left: 180, portal_mismatches: [] },
  } as unknown as RequestState
}

export function useBoardDemo(enabled: boolean): RequestState | null {
  const [state, setState] = useState<RequestState | null>(null)
  useEffect(() => {
    if (!enabled) return
    let start = Date.now() / 1000
    const tick = () => {
      const t = Date.now() / 1000 - start
      if (t > LOOP) start = Date.now() / 1000
      setState(build(Math.min(t, LOOP), start))
    }
    tick()
    const id = setInterval(tick, 400)
    return () => clearInterval(id)
  }, [enabled])
  return state
}
