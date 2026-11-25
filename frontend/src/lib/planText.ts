import type { RequestState } from '../types'
import { km } from '../components/bits'

/** Plain-text plan for pasting into a message or a chart note. Keeps the truthfulness rules in the text itself. */
export function planText(st: RequestState): string {
  const r = st.request
  const p = st.plan
  const demo = p.allocation.some((a) => a.route === 'demo')
  const out: string[] = []
  out.push(`${r.units} × ${r.blood_group} ${p.component_label} for ${st.hospital.name}`)
  out.push(p.short_by ? `Confirmed ${Math.min(p.confirmed, p.needed)} of ${p.needed}; short by ${p.short_by}.` : `Target met: ${p.needed} of ${p.needed}.`)
  if (demo) out.push('NOTE: the demo line answered for these banks, not the banks themselves. Phone each bank to verify.')
  if (p.allocation.length) {
    out.push('', 'Collect from:')
    p.allocation.forEach((a, i) => {
      const when = a.eta_min != null ? `~${a.eta_min} min` : km(a.distance_km)
      out.push(`${i + 1}. ${a.bank_name}: ${a.units} × ${a.group}${a.exact_match ? '' : ' (compatible)'}, ${when}${a.hold_hours ? `, held ${a.hold_hours} h` : ''}`)
    })
  }
  if (p.steps.length) out.push('', ...p.steps.map((s) => `- ${s}`))
  if (p.leads.length) {
    out.push('', 'Unverified leads, call yourself:')
    p.leads.forEach((l) => out.push(`- ${l.bank_name}${l.phone ? `: ${l.phone}` : ''}`))
  }
  out.push('', 'Final compatibility is decided only by the crossmatch at the issuing bank.')
  return out.join('\n')
}

/** Walking/driving directions link from the bank's coordinates; null when the bank isn't confidently located. */
export function directionsUrl(lat?: number | null, lng?: number | null): string | null {
  if (lat == null || lng == null) return null
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`
}
