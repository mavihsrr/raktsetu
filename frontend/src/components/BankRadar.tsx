import type { Call } from '../types'

interface Props {
  hospital: { lat?: number | null; lng?: number | null; name: string }
  calls: Call[]
  radiusKm: number
}

const GOLDEN = 2.399963 // spreads banks without coordinates evenly around the hospital

function colour(c: Call): string {
  if (c.status === 'dialing') return 'var(--blue)'
  if (c.status === 'completed') return c.confirmed_units + c.alt_units > 0 ? 'var(--green)' : 'var(--faint)'
  if (c.status === 'queued') return 'var(--muted)'
  return 'var(--red)'
}

/** Hospital at the centre, banks by distance. Direction comes from lat/lng when known; distance is always real. */
export function BankRadar({ hospital, calls, radiusKm }: Props) {
  const banks = calls.filter((c) => c.target_type === 'bank' && c.distance_km != null)
  const hidden = calls.filter((c) => c.target_type === 'bank').length - banks.length
  if (!banks.length) return null
  const maxKm = Math.max(radiusKm, ...banks.map((b) => b.distance_km as number)) * 1.05
  const R = 96
  const cx = 120
  const cy = 108
  const hLat = hospital.lat
  const hLng = hospital.lng

  const pts = banks.map((b, i) => {
    let ang = i * GOLDEN
    if (hLat != null && hLng != null && b.lat != null && b.lng != null) {
      ang = Math.atan2((b.lng - hLng) * Math.cos((hLat * Math.PI) / 180), b.lat - hLat)
    }
    const r = Math.max(0.14, (b.distance_km as number) / maxKm) * R
    return { b, x: cx + Math.sin(ang) * r, y: cy - Math.cos(ang) * r }
  })
  const rings = [0.5, 1].map((f) => ({ f, km: Math.round(maxKm * f) }))

  return (
    <figure className="radar" aria-label={`Banks by distance from ${hospital.name}`}>
      <svg viewBox="0 0 240 216" role="img" aria-hidden="true">
        {rings.map(({ f, km }) => (
          <g key={f}>
            <circle cx={cx} cy={cy} r={R * f} className="radar-ring" />
            <text x={cx + 4} y={cy - R * f + 11} className="radar-km">{km} km</text>
          </g>
        ))}
        <circle cx={cx} cy={cy} r={(radiusKm / maxKm) * R} className="radar-search" />
        {pts.map(({ b, x, y }) => (
          <g key={b.id} className={`radar-dot ${b.status === 'dialing' ? 'is-dialing' : ''}`} transform={`translate(${x} ${y})`}>
            <title>{`${b.target_name} · ${b.distance_km} km`}</title>
            {b.status === 'dialing' && <circle r="6" className="radar-ping" style={{ stroke: colour(b) }} />}
            <circle r="4.2" style={{ fill: colour(b) }} className={b.route === 'lead' ? 'is-lead' : ''} />
          </g>
        ))}
        <circle cx={cx} cy={cy} r="5" className="radar-home" />
      </svg>
      <figcaption className="radar-cap">
        <span><i className="dotk" style={{ background: 'var(--blue)' }} /> calling</span>
        <span><i className="dotk" style={{ background: 'var(--green)' }} /> confirmed</span>
        <span><i className="dotk" style={{ background: 'var(--muted)' }} /> queued</span>
        {hidden > 0 && <span className="muted">{hidden} without distance</span>}
      </figcaption>
    </figure>
  )
}
