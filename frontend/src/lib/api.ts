import type { Flags, RequestRow, RequestState } from '../types'

// Base URL from env (empty = same origin, which is how the dev proxy and FastAPI-served build work).
const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? ''

function readToken(): string {
  const fromHash = new URLSearchParams(location.hash.slice(1)).get('token')
  if (fromHash) {
    try { sessionStorage.setItem('raktsetu.token', fromHash) } catch { /* private mode */ }
    // keep the token out of the address bar, history and screenshots
    history.replaceState(null, '', location.pathname + location.search)
    return fromHash
  }
  try { return sessionStorage.getItem('raktsetu.token') ?? '' } catch { return '' }
}
export const TOKEN = readToken()

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(TOKEN ? { 'X-Dashboard-Token': TOKEN } : {}), ...init.headers },
  })
  if (!res.ok) throw new Error((await res.text()) || res.statusText)
  return res.json() as Promise<T>
}

export const api = {
  flags: () => call<Flags>('/api/flags'),
  requests: () => call<RequestRow[]>('/api/requests'),
  request: (id: string) => call<RequestState>(`/api/requests/${encodeURIComponent(id)}`),
  create: (body: Record<string, unknown>) =>
    call<{ ok: boolean; request_id?: string; say: string }>('/api/requests', { method: 'POST', body: JSON.stringify(body) }),
  start: (id: string) => call<{ ok: boolean; say?: string }>(`/api/requests/${encodeURIComponent(id)}/start`, { method: 'POST' }),
  approve: (id: string) => call<{ ok: boolean; say?: string }>(`/api/requests/${encodeURIComponent(id)}/approve`, { method: 'POST' }),
  cancel: (id: string) => call<{ ok: boolean; say?: string }>(`/api/requests/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
}

export function streamUrl(): string {
  return `${BASE}/api/stream${TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : ''}`
}

export function voiceSocketUrl(): string {
  const origin = BASE || location.origin
  const ws = origin.replace(/^http/, 'ws')
  return `${ws}/api/voice/ws${TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : ''}`
}
