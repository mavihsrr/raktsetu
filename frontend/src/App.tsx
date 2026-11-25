import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './app.css'
import { LiveStatus } from './components/LiveStatus'
import { Stage } from './components/Stage'
import { TopBar } from './components/TopBar'
import { Transcript } from './components/Transcript'
import { useLive } from './hooks/useLive'
import { usePanels } from './hooks/usePanels'
import { orbDemo } from './lib/orbDemo'
import { useBoardDemo } from './lib/boardDemo'
import { VoiceSession, type Levels, type VoiceLine, type VoiceState } from './lib/voice'

const SILENT: Levels = { mic: 0, out: 0, micBands: [0, 0, 0], outBands: [0, 0, 0] }

export default function App() {
  const inVoice = useRef(false)
  const live = useLive(() => inVoice.current)
  // dev-only fixture (#boarddemo) so the call board can be tuned without placing calls
  const boardDemo = useBoardDemo(import.meta.env.DEV && location.hash.includes('boarddemo'))
  const view = boardDemo ?? live.state
  const panels = usePanels()
  const [vstate, setVState] = useState<VoiceState>('idle')
  const [detail, setDetail] = useState<string>()
  const [lines, setLines] = useState<VoiceLine[]>([])
  const [muted, setMuted] = useState(false)
  const session = useRef<VoiceSession | null>(null)
  const [sessionStart, setSessionStart] = useState(0) // index into lines where this session began
  const [bloomKey, setBloomKey] = useState(0)
  const [pebbleKey, setPebbleKey] = useState(0)
  const demo = useRef<ReturnType<typeof orbDemo> | null>(null)
  const linesLen = useRef(0)
  linesLen.current = lines.length

  useEffect(() => {
    if (!import.meta.env.DEV || !location.hash.includes('orbdemo')) return
    demo.current = orbDemo((s) => { setVState(s); if (s === 'connecting') setPebbleKey((k) => k + 1) }, () => setBloomKey((k) => k + 1))
    return () => { demo.current?.stop(); demo.current = null }
  }, [])

  useEffect(() => () => session.current?.stop(), [])

  const levels = useCallback(() => demo.current?.levels() ?? session.current?.levels() ?? SILENT, [])

  const start = useCallback((o: { name: string; hospital: string; language: string }) => {
    session.current?.stop()
    setDetail(undefined)
    setSessionStart(linesLen.current)
    setPebbleKey((k) => k + 1) // the pebble drop: starting a session ripples out from the orb
    setPebbleKey((k) => k + 1)
    const s = new VoiceSession({
      onState: (st, d) => { setVState(st); if (d) setDetail(d) },
      onLine: (l) => setLines((prev) => [...prev, l]),
    })
    session.current = s
    setMuted(false)
    s.start(o)
  }, [])

  const stop = useCallback(() => { session.current?.stop(); session.current = null }, [])

  const toggleMute = useCallback(() => {
    const s = session.current
    if (!s) return
    s.muted = !s.muted
    setMuted(s.muted)
  }, [])

  inVoice.current = vstate !== 'idle' && vstate !== 'error'
  const events = useMemo(() => {
    const own = view?.events ?? []
    const seen = new Set(own.map((e) => e.seq))
    return [...own, ...live.progress.filter((e) => !seen.has(e.seq))]
  }, [view, live.progress])
  const latestProgress = live.progress.length ? live.progress[live.progress.length - 1].say : undefined

  // a bank confirming units makes the orb bloom green (only for confirmations that arrive while watching)
  const seen = useRef<{ rid: string | null; max: number }>({ rid: null, max: 0 })
  useEffect(() => {
    const rid = view?.request.id ?? null
    const max = events.reduce((m, e) => Math.max(m, e.seq), 0)
    if (seen.current.rid !== rid) { seen.current = { rid, max }; return }
    if (events.some((e) => e.seq > seen.current.max && e.type === 'bank_confirmed')) setBloomKey((k) => k + 1)
    seen.current.max = Math.max(seen.current.max, max)
  }, [events, view?.request.id])

  const caption = lines.length > sessionStart ? lines[lines.length - 1] : undefined

  // with live status collapsed, anything that needs the coordinator surfaces as a pill on the stage
  const st = view
  const peek = !panels.open.right && st
    ? (() => {
        const r = st.request
        const units = `${Math.min(st.plan.confirmed, st.plan.needed)}/${st.plan.needed} units`
        const onCall = st.calls.filter((c) => c.status === 'dialing').length
        if (r.status === 'planned') return { tone: 'blue', text: `Leads ready · ${r.units}× ${r.blood_group}`, action: 'Review' }
        if (r.status === 'awaiting_wave2') return { tone: 'amber', text: `Needs approval · ${units}`, action: 'Review' }
        if (r.status === 'calling') return { tone: 'blue', text: `${onCall} on call · ${units}`, action: 'Open' }
        if (r.status === 'resolved') return { tone: 'green', text: `Plan ready · ${units}${st.plan.allocation.some((a) => a.route === 'demo') ? ' (demo line)' : ''}`, action: 'Open' }
        return null
      })()
    : null

  return (
    <div className="app">
      <TopBar flags={live.flags} flagsError={live.flagsError} health={live.health} />
      <main className={`grid ${panels.open.left ? '' : 'left-closed'} ${panels.open.right ? '' : 'right-closed'}`}>
        <Transcript lines={lines} events={events} open={panels.open.left} onToggle={() => panels.toggle('left')} />
        <Stage
          state={vstate}
          detail={detail}
          levels={levels}
          caption={caption}
          bloomKey={bloomKey}
          pebbleKey={pebbleKey}
          progress={latestProgress}
          peek={peek ? { ...peek, onOpen: () => panels.toggle('right', true) } : undefined}
          muted={muted}
          voiceReady={live.flags ? live.flags.voice_ready : undefined}
          onStart={start}
          onStop={stop}
          onMute={toggleMute}
        />
        <LiveStatus
          list={live.list}
          selected={live.selected}
          onSelect={live.setSelected}
          state={view}
          onChanged={live.refresh}
          loadError={live.loadError}
          open={panels.open.right}
          onToggle={() => panels.toggle('right')}
          flags={live.flags}
          progress={live.progress}
        />
      </main>
    </div>
  )
}
