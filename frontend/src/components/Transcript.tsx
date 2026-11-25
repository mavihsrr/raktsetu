import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, Info, Loader, PhoneCall, PhoneOutgoing, Radar, Search, XCircle } from 'lucide-react'
import type { VoiceLine } from '../lib/voice'
import type { BackendEvent } from '../types'
import { clock } from './bits'
import { CollapseButton, Rail } from './Rail'

type Item =
  | { kind: 'voice'; id: string; ts: number; role: 'user' | 'agent'; text: string }
  | { kind: 'event'; id: string; ts: number; type: string; text: string }

const EVENT_ICON: Record<string, typeof Info> = {
  leads_found: Search,
  calls_started: PhoneOutgoing,
  call_started: PhoneOutgoing,
  bank_result: PhoneCall,
  donor_result: PhoneCall,
  bank_confirmed: CheckCircle2,
  target_met: CheckCircle2,
  approval_needed: AlertCircle,
  progress: Loader,
  resolved: CheckCircle2,
  unresolved: AlertCircle,
  wave1_done: Info,
  paused: AlertCircle,
  resumed: PhoneOutgoing,
  wave2_started: Radar,
  cancelled: XCircle,
}

interface Props {
  lines: VoiceLine[]
  events: BackendEvent[]
  open: boolean
  onToggle: () => void
}

export function Transcript({ lines, events, open, onToggle }: Props) {
  const end = useRef<HTMLDivElement>(null)
  const seen = useRef(0)

  const items = useMemo<Item[]>(() => {
    const ev: Item[] = events
      .filter((e) => e.say)
      .map((e) => ({ kind: 'event', id: `e${e.seq}`, ts: e.ts, type: e.type, text: e.say }))
    const vo: Item[] = lines.map((l) => ({ kind: 'voice', ...l }))
    return [...ev, ...vo].sort((a, b) => a.ts - b.ts)
  }, [lines, events])

  useEffect(() => {
    if (open) {
      seen.current = items.length
      end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [items.length, open])

  if (!open) {
    const unread = items.length - seen.current
    const lastVoice = [...items].reverse().find((i) => i.kind === 'voice')
    return (
      <section className="col col-transcript is-collapsed" aria-label="Conversation (collapsed)">
        <Rail side="left" label="Conversation" shortcut="[" onOpen={onToggle}>
          {unread > 0 && <span className="rail-badge num">{unread}</span>}
          {lastVoice && <span className={`rail-dot rail-dot-${lastVoice.kind === 'voice' ? lastVoice.role : ''}`} />}
        </Rail>
      </section>
    )
  }

  return (
    <section className="col col-transcript" aria-label="Conversation">
      <header className="col-head">
        <h2>Conversation</h2>
        <span className="head-count num">{items.length > 0 ? items.length : ''}</span>
        <CollapseButton side="left" label="conversation" shortcut="[" onClick={onToggle} />
      </header>
      <div className="col-scroll" aria-live="polite">
        {items.length === 0 ? (
          <div className="empty">
            <p>Your conversation with RaktSetu appears here, along with every call update as it happens.</p>
            <p className="muted small">Try: “Need 2 units of B-positive at KIMS Hospital Hubli, surgery in 3 hours.”</p>
          </div>
        ) : (
          <ol className="timeline">
            {items.map((it) =>
              it.kind === 'voice' ? (
                <li key={it.id} className={`msg msg-${it.role}`}>
                  <span className="msg-who">{it.role === 'user' ? 'You' : 'RaktSetu'} <time>{clock(it.ts)}</time></span>
                  <p>{it.text}</p>
                </li>
              ) : (
                <EventItem key={it.id} type={it.type} text={it.text} ts={it.ts} />
              ),
            )}
          </ol>
        )}
        <div ref={end} />
      </div>
    </section>
  )
}

/** Backend updates are long sentences; fold them to three lines with a toggle. */
function EventItem({ type, text, ts }: { type: string; text: string; ts: number }) {
  const [full, setFull] = useState(false)
  const long = text.length > 150
  return (
    <li className={`evt evt-${type}`}>
      <EventIcon type={type} />
      <div className="evt-body">
        <p className={long && !full ? 'clamp' : ''}>{text}</p>
        {long && <button className="evt-more" onClick={() => setFull(!full)} aria-expanded={full}>{full ? 'Less' : 'More'}</button>}
      </div>
      <time>{clock(ts)}</time>
    </li>
  )
}

function EventIcon({ type }: { type: string }) {
  const Icon = EVENT_ICON[type] ?? Info
  return <Icon size={14} className="evt-icon" aria-hidden />
}
