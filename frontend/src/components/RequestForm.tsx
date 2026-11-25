import { useState } from 'react'
import { api } from '../lib/api'

/** Typed fallback when the mic is unavailable: same backend flow as voice. */
export function RequestForm({ onCreated, onCancel }: { onCreated: (id: string) => void; onCancel?: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setErr('')
    const body = Object.fromEntries(new FormData(e.currentTarget))
    try {
      const r = await api.create(body)
      if (!r.ok || !r.request_id) setErr(r.say || 'The request could not be created.')
      else onCreated(r.request_id)
    } catch {
      setErr('Could not reach the backend. Check that it is running.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="rform" onSubmit={submit}>
      <label className="span2">Where is the patient?
        <input name="location" required placeholder="Hospital and town, e.g. KIMS Hospital Hubli" autoComplete="off" />
      </label>
      <label>Blood group
        <select name="blood_group" defaultValue="B+">
          {['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map((g) => <option key={g}>{g}</option>)}
        </select>
      </label>
      <label>Units
        <input name="units" type="number" min={1} max={20} defaultValue={2} required />
      </label>
      <label>Component
        <select name="component" defaultValue="packed_red_cells">
          <option value="packed_red_cells">Packed red cells</option>
          <option value="whole_blood">Whole blood</option>
          <option value="platelets">Platelets</option>
        </select>
      </label>
      <label>Needed within (hours)
        <input name="deadline_hours" type="number" min={0.5} step={0.5} defaultValue={3} />
      </label>
      {err && <p className="form-err span2" role="alert">{err}</p>}
      <div className="span2 form-actions">
        {onCancel && <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>}
        <button className="btn btn-primary" disabled={busy}>{busy ? 'Checking e-RaktKosh…' : 'Find blood banks'}</button>
      </div>
    </form>
  )
}
