export type RequestStatus = 'planned' | 'calling' | 'awaiting_wave2' | 'resolved' | 'unresolved' | 'cancelled'
export type CallStatus = 'queued' | 'dialing' | 'completed' | 'no_answer' | 'busy' | 'failed' | 'skipped' | string
export type Route = 'real' | 'demo' | 'lead' | null | undefined

export interface RequestRow {
  id: string
  blood_group: string
  units: number
  component: string
  status: RequestStatus
  hospital_name: string
  confirmed_units: number
  created_at: number
  deadline_at?: number | null
}

export interface TranscriptLine { role: string; text: string }

export interface Call {
  id: string
  target_id: string
  target_type: 'bank' | 'donor'
  target_name: string
  status: CallStatus
  route?: Route
  mode?: string | null
  wave: number
  distance_km: number | null
  portal_units: number | null
  confirmed_units: number
  alt_units: number
  alt_group?: string | null
  hold_hours?: number | null
  phone?: string | null
  notes?: string | null
  willing?: 'yes' | 'no' | 'later' | string | null
  lat?: number | null
  lng?: number | null
  queued_at?: number | null
  started_at?: number | null
  ended_at?: number | null
  transcript?: TranscriptLine[] | null
}

export interface PlanItem {
  bank_name: string
  units: number
  group: string
  exact_match: boolean
  distance_km: number | null
  eta_min: number | null
  hold_hours?: number | null
  route?: Route
  mode?: string
}

export interface Plan {
  needed: number
  confirmed: number
  short_by: number
  group: string
  component_label: string
  allocation: PlanItem[]
  backups: PlanItem[]
  leads: { bank_name: string; portal: number | null; distance_km: number | null; phone?: string | null; why?: string }[]
  steps: string[]
  late_vs_deadline: string[]
  deadline_minutes_left: number | null
  portal_mismatches: { bank_name: string; portal: number | null; phone: number }[]
}

export interface BackendEvent {
  seq: number
  request_id: string
  ts: number
  type: string
  payload: string | Record<string, unknown>
  say: string
}

export interface BankView {
  id: string
  name: string
  address?: string | null
  phone?: string | null
  lat?: number | null
  lng?: number | null
  distance_km: number | null
  portal_units: number
  portal_exact?: number
  portal_updated_at?: string | null
  portal_stale?: boolean
  call_status?: string | null
  route?: Route
}

/** Banks as first reported by e-RaktKosh (before distances exist). */
export interface PortalBank {
  id: string
  name: string
  address?: string | null
  phone?: string | null
  portal_units: number
  stale?: boolean
  updated?: string | null
}

export interface RequestState {
  request: RequestRow & { wave: number; bank_radius_km: number; wave2_radius_km?: number; area_label?: string | null }
  hospital: { name: string; lat?: number | null; lng?: number | null }
  calls: Call[]
  plan: Plan
  counts: Record<string, number>
  needs_approval: boolean
  done: boolean
  events: BackendEvent[]
  banks?: BankView[]
}

export interface Flags {
  values: {
    outbound_calls_enabled: boolean
    call_mode: 'simulated' | 'live'
    max_parallel_calls: number
    autopilot_mode: boolean
    bank_radius_km: number
    call_real_banks: boolean
    call_donors?: boolean
    donor_radius_km?: number
    wave2_radius_multiplier?: number
    max_banks_per_wave?: number
  }
  overridden?: string[]
  /** counts only, never numbers */
  demo_lines?: { banks: number; donors: number }
  source: string
  sarvam_configured: boolean
  voice_ready?: boolean
  live_targets: string[]
}
