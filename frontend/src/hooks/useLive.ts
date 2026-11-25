import { useCallback, useEffect, useRef, useState } from 'react'
import { api, streamUrl } from '../lib/api'
import type { BackendEvent, Flags, RequestRow, RequestState } from '../types'

export type StreamHealth = 'connecting' | 'live' | 'reconnecting'

/** Requests, the selected request's full state, operator flags, and the SSE stream that keeps them fresh. */
export function useLive(follow: () => boolean = () => false) {
  const [flags, setFlags] = useState<Flags | null>(null)
  const [flagsError, setFlagsError] = useState(false)
  const [list, setList] = useState<RequestRow[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [state, setState] = useState<RequestState | null>(null)
  const [health, setHealth] = useState<StreamHealth>('connecting')
  const [loadError, setLoadError] = useState<string | null>(null)
  const selectedRef = useRef<string | null>(null)
  selectedRef.current = selected
  const followRef = useRef(follow)
  followRef.current = follow
  // live search progress ("Searching…", "Found district…") arrives before the request row exists
  const [progress, setProgress] = useState<BackendEvent[]>([])
  // requests whose search already finished: their later progress lines belong to the request view
  const doneRids = useRef(new Set<string>())
  const listRef = useRef<RequestRow[]>([])
  listRef.current = list

  // a search that dies (map or portal down) must not leave a spinner on screen
  useEffect(() => {
    const id = setInterval(() => {
      const cutoff = Date.now() / 1000 - 90
      setProgress((prev) => (prev.some((p) => p.ts <= cutoff) ? prev.filter((p) => p.ts > cutoff) : prev))
    }, 5000)
    return () => clearInterval(id)
  }, [])

  const loadList = useCallback(async () => {
    try {
      const rows = await api.requests()
      setList(rows)
      setLoadError(null)
      // no auto-select: every visit starts clean; a request opens when it is created here or picked from the list
    } catch {
      setLoadError('Cannot reach the RaktSetu backend.')
    }
  }, [])

  const loadState = useCallback(async () => {
    const id = selectedRef.current
    if (!id) return setState(null)
    try {
      const st = await api.request(id)
      if (selectedRef.current === id) setState(st)
    } catch { /* keep the last good state */ }
  }, [])

  const refresh = useCallback(async () => { await Promise.all([loadList(), loadState()]) }, [loadList, loadState])

  useEffect(() => { loadState() }, [selected, loadState])

  // flags every 5 s (Flagsmith is re-read server-side with a short TTL)
  useEffect(() => {
    const tick = () => api.flags().then((f) => { setFlags(f); setFlagsError(false) }).catch(() => setFlagsError(true))
    tick()
    const id = setInterval(tick, 5000)
    return () => clearInterval(id)
  }, [])

  // SSE: any event refreshes; a new request found by voice becomes the selection
  useEffect(() => {
    loadList()
    let pending: ReturnType<typeof setTimeout> | null = null
    const schedule = () => {
      if (pending) return
      pending = setTimeout(() => { pending = null; refresh() }, 150)
    }
    const es = new EventSource(streamUrl())
    es.onopen = () => setHealth('live')
    es.onerror = () => setHealth('reconnecting')
    es.addEventListener('update', (ev) => {
      const e = JSON.parse((ev as MessageEvent).data) as BackendEvent
      if (e.type === 'progress' && e.say && !doneRids.current.has(e.request_id)
          && !listRef.current.some((r) => r.id === e.request_id)) {
        const cutoff = Date.now() / 1000 - 90
        setProgress((prev) => [...prev.filter((p) => p.ts > cutoff && p.seq !== e.seq), e].slice(-16))
      }
      if (e.type === 'leads_found') {
        doneRids.current.add(e.request_id)
        // the DB copy of these progress lines now comes with the request's own events
        setProgress((prev) => prev.filter((p) => p.request_id !== e.request_id))
        // only follow a new request when this tab is the one asking (others' requests stay private)
        if (followRef.current()) setSelected(e.request_id)
      }
      schedule()
    })
    return () => { es.close(); if (pending) clearTimeout(pending) }
  }, [loadList, refresh])

  // belt and braces while calls are in flight (SSE can lag behind a proxy)
  useEffect(() => {
    if (state?.request.status !== 'calling') return
    const id = setInterval(loadState, 4000)
    return () => clearInterval(id)
  }, [state?.request.status, loadState])

  return { flags, flagsError, list, selected, setSelected, state, health, loadError, refresh, progress }
}
