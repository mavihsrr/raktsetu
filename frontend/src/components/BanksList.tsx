import { useState } from 'react'
import { Phone } from 'lucide-react'
import type { BankView, PortalBank } from '../types'
import { RouteBadge, km } from './bits'

type Row = {
  id: string; name: string; address?: string | null; phone?: string | null
  distance_km?: number | null; units: number; stale?: boolean; updated?: string | null
  route?: BankView['route']; callStatus?: string | null
}

function ago(iso?: string | null): string {
  if (!iso) return ''
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6
  return h < 1 ? 'updated just now' : h < 48 ? `updated ${Math.round(h)} h ago` : `updated ${Math.round(h / 24)} d ago`
}

/** Every blood bank e-RaktKosh returned for the district, with portal stock, phone and live distance. */
export function BanksList({ banks, portal, locating, group }: { banks?: BankView[]; portal?: PortalBank[]; locating?: boolean; group?: string }) {
  const [all, setAll] = useState(false)
  const rows: Row[] = banks?.length
    ? banks.map((b) => ({ id: b.id, name: b.name, address: b.address, phone: b.phone, distance_km: b.distance_km,
        units: b.portal_units, stale: b.portal_stale, updated: b.portal_updated_at, route: b.route, callStatus: b.call_status }))
    : (portal ?? []).map((b) => ({ id: b.id, name: b.name, address: b.address, phone: b.phone, distance_km: undefined,
        units: b.portal_units, stale: b.stale, updated: b.updated }))
  if (!rows.length) return null
  const shown = all ? rows : rows.slice(0, 8)
  const located = rows.filter((r) => r.distance_km != null).length
  return (
    <div className="block">
      <div className="block-head">
        <h3 className="block-title">All blood banks found ({rows.length})</h3>
        <span className="counts num">{located}/{rows.length} distances</span>
      </div>
      <p className="muted small">Live from e-RaktKosh{group ? `, stock for ${group} and compatible groups` : ''}. Portal stock is a lead, not a fact.</p>
      <ul className="banks">
        {shown.map((b) => {
          const phone = (b.phone ?? '').split(',')[0].trim()
          return (
            <li key={b.id} className="bank">
              <div className="bank-main">
                <span className="bank-name">{b.name} <RouteBadge route={b.route} /></span>
                {b.address && <span className="bank-addr">{b.address}</span>}
                <span className="bank-meta">
                  {phone && <a className="mono" href={`tel:${phone}`}><Phone size={11} aria-hidden /> {phone}</a>}
                  {b.updated && <span className={b.stale ? 'tag tag-amber' : 'muted'}>{ago(b.updated)}{b.stale ? ' · stale' : ''}</span>}
                </span>
              </div>
              <div className="bank-nums num">
                <span className="bank-dist">
                  {b.distance_km != null ? km(b.distance_km) : locating ? 'calculating…' : 'distance unknown'}
                </span>
                <span className={b.units > 0 && !b.stale ? 'bank-stock' : 'bank-stock is-zero'}>{b.units} units</span>
              </div>
            </li>
          )
        })}
      </ul>
      {rows.length > 8 && (
        <button className="btn btn-ghost" onClick={() => setAll((v) => !v)}>{all ? 'Show fewer' : `Show all ${rows.length}`}</button>
      )}
    </div>
  )
}
