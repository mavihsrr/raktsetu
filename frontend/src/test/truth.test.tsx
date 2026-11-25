import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CallRow } from '../components/CallRow'
import { callRoute } from '../lib/route'
import { directionsUrl, planText } from '../lib/planText'
import type { Call, Flags, RequestState } from '../types'

const call = (over: Partial<Call>): Call => ({
  id: 'c1', target_id: 'B1', target_type: 'bank', target_name: 'Test Blood Bank', status: 'completed', wave: 1,
  distance_km: 2.5, portal_units: 4, confirmed_units: 1, alt_units: 0, ...over,
}) as Call

const flags = (v: Partial<Flags['values']>, extra: Partial<Flags> = {}): Flags => ({
  values: { outbound_calls_enabled: true, call_mode: 'live', max_parallel_calls: 5, autopilot_mode: false, bank_radius_km: 8, call_real_banks: false, ...v },
  source: 'test', sarvam_configured: true, live_targets: [], demo_lines: { banks: 1, donors: 1 }, ...extra,
}) as Flags

describe('where calls ring (never imply real banks were phoned)', () => {
  it('is leads-only when calling is simulated', () => expect(callRoute(flags({ call_mode: 'simulated' }))).toBe('none'))
  it('is the demo line when live but real banks are off', () => expect(callRoute(flags({}))).toBe('demo'))
  it('is real only when Flagsmith call_real_banks is on', () => expect(callRoute(flags({ call_real_banks: true }))).toBe('real'))
  it('is leads-only when Sarvam is not configured', () => expect(callRoute(flags({}, { sarvam_configured: false }))).toBe('none'))
  it('is leads-only with no flags loaded', () => expect(callRoute(null)).toBe('none'))
})

describe('call rows', () => {
  it('a donor who declined is not shown as willing', () => {
    render(<CallRow c={call({ target_type: 'donor', willing: 'no', confirmed_units: 0 })} />)
    expect(screen.getByText('Declined')).toBeTruthy()
    expect(screen.queryByText(/will donate/i)).toBeNull()
  })
  it('a willing donor is labelled restock, not patient units', () => {
    render(<CallRow c={call({ target_type: 'donor', willing: 'yes', confirmed_units: 0 })} />)
    expect(screen.getByText('Will donate (restock)')).toBeTruthy()
  })
  it('a demo-line answer says the bank itself did not answer', () => {
    render(<CallRow c={call({ route: 'demo', mode: 'live' })} />)
    expect(screen.getByText(/demo line answered, not the bank/i)).toBeTruthy()
  })
  it('no portal-vs-phone mismatch is claimed for a demo-line answer', () => {
    render(<CallRow c={call({ route: 'demo', portal_units: 9, confirmed_units: 1 })} />)
    expect(screen.queryByText(/portal 9 ≠ phone 1/)).toBeNull()
  })
  it('a real mismatch is shown when the bank itself answered', () => {
    render(<CallRow c={call({ route: 'real', portal_units: 9, confirmed_units: 1 })} />)
    expect(screen.getByText(/portal 9 ≠ phone 1/)).toBeTruthy()
  })
  it('an unknown distance says so instead of guessing', () => {
    render(<CallRow c={call({ distance_km: null })} />)
    expect(screen.getByText('distance unknown')).toBeTruthy()
  })
})

const state = (allocRoute: string | undefined): RequestState => ({
  request: { id: 'R1', blood_group: 'B+', units: 2 },
  hospital: { name: 'City Hospital' },
  plan: {
    needed: 2, confirmed: 1, short_by: 1, group: 'B+', component_label: 'packed red cells', backups: [], leads: [],
    steps: ['Send the patient sample and requisition to the bank for crossmatch.'], late_vs_deadline: [],
    allocation: [{ bank_name: 'Bank A', units: 1, group: 'B+', exact_match: true, distance_km: 3, eta_min: 12, route: allocRoute }],
  },
}) as unknown as RequestState

describe('plan text', () => {
  it('always ends with the crossmatch rule and never says blood is reserved', () => {
    const t = planText(state('real'))
    expect(t).toMatch(/crossmatch/i)
    expect(t).not.toMatch(/reserved/i)
  })
  it('warns when the demo line answered for the banks', () => expect(planText(state('demo'))).toMatch(/demo line answered/i))
  it('does not warn for real bank answers', () => expect(planText(state('real'))).not.toMatch(/demo line answered/i))
  it('states a shortfall plainly', () => expect(planText(state('real'))).toMatch(/short by 1/i))
})

describe('directions', () => {
  it('never guesses a location', () => {
    expect(directionsUrl(null, 75.1)).toBeNull()
    expect(directionsUrl(15.3, undefined)).toBeNull()
  })
  it('links to the bank when it is located', () => expect(directionsUrl(15.36, 75.12)).toContain('destination=15.36,75.12'))
})
