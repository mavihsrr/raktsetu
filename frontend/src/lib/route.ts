import type { Flags } from '../types'

/** Where "start calling" will actually ring, mirroring app/coordinator.py `_routing`:
 *  real = the bank's own number; demo = our demo phone stands in; none = banks are listed as leads, nobody is phoned. */
export type CallRoute = 'real' | 'demo' | 'none'

export function callRoute(f: Flags | null): CallRoute {
  if (!f) return 'none'
  const live = f.values.call_mode === 'live' && f.sarvam_configured
  if (live && f.values.call_real_banks) return 'real'
  if (live && (f.demo_lines?.banks ?? 0) > 0) return 'demo'
  return 'none'
}
