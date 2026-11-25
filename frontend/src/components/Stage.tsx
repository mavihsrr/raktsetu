import { useRef } from 'react'
import { ChevronRight, Mic, MicOff, PhoneOff, RotateCcw } from 'lucide-react'
import type { Levels, VoiceLine, VoiceState } from '../lib/voice'
import { Orb } from './Orb'

const LABEL: Record<VoiceState, string> = {
  idle: 'Start a voice session',
  connecting: 'Connecting to RaktSetu…',
  listening: 'Listening',
  user: 'Hearing you',
  thinking: 'Working on it',
  speaking: 'RaktSetu is speaking',
  error: 'Voice unavailable',
}

const HINT: Partial<Record<VoiceState, string>> = {
  idle: 'Say what blood you need, how many units, where, and by when.',
  connecting: 'Opening the microphone and the agent. This takes a few seconds.',
  listening: 'Go ahead. You can interrupt the agent at any time.',
  speaking: 'Talk over it to interrupt.',
  thinking: 'Checking banks and live stock.',
}

interface Props {
  state: VoiceState
  detail?: string
  levels: () => Levels
  /** Latest line said in this session, shown as a live caption under the orb. */
  caption?: VoiceLine
  /** Bumps when a bank confirms units. */
  bloomKey: number
  /** Bumps when a session starts: the pebble drop. */
  pebbleKey: number
  /** Latest live search step from the backend, shown while the agent works. */
  progress?: string
  /** Shown when the live-status panel is collapsed and something needs attention. */
  peek?: { tone: string; text: string; action: string; onOpen: () => void }
  muted: boolean
  voiceReady: boolean | undefined
  onStart: (o: { name: string; hospital: string; language: string }) => void
  onStop: () => void
  onMute: () => void
}

export function Stage({ state, detail, levels, caption, bloomKey, pebbleKey, progress, peek, muted, voiceReady, onStart, onStop, onMute }: Props) {
  const anchor = useRef<HTMLButtonElement>(null)
  const active = state !== 'idle' && state !== 'error'

  // the agent greets generically and asks for what it needs; it detects the spoken language itself
  function start() {
    onStart({ name: '', hospital: '', language: 'English' })
  }

  return (
    <section className={`col stage stage-${state}`} aria-label="Voice">
      <Orb state={state} levels={levels} anchor={anchor} bloomKey={bloomKey} pebbleKey={pebbleKey} />
      {peek && (
        <button className={`peek peek-${peek.tone}`} onClick={peek.onOpen}>
          <span className="peek-dot" aria-hidden />
          <span className="num">{peek.text}</span>
          <span className="peek-action">{peek.action} <ChevronRight size={14} aria-hidden /></span>
        </button>
      )}
      <div className="orb-wrap">
        <button
          ref={anchor}
          className="orb-hit"
          onClick={active ? undefined : start}
          disabled={active || voiceReady === false}
          aria-label={active ? LABEL[state] : 'Start voice session'}
        />
      </div>

      <div className="stage-text" role="status">
        <p key={state} className="stage-label">{LABEL[state]}</p>
        {active && caption ? (
          <p key={caption.id} className={`caption caption-${caption.role}`} aria-live="polite">
            {caption.text.split(/\s+/).map((w, i) => (
              <span key={i} style={{ animationDelay: `${Math.min(i * 45, 1800)}ms` }}>{w} </span>
            ))}
          </p>
        ) : (
          <p className="stage-hint">
            {state === 'error'
              ? detail
              : voiceReady === false
                ? 'Voice is not configured on the server. Use the typed request instead.'
                : state === 'thinking' && progress ? progress : HINT[state]}
          </p>
        )}
      </div>

      {active ? (
        <div className="controls">
          <button className={`round ${muted ? 'round-on' : ''}`} onClick={onMute} aria-pressed={muted} aria-label={muted ? 'Unmute microphone' : 'Mute microphone'}>
            {muted ? <MicOff size={20} /> : <Mic size={20} />}
          </button>
          <button className="round round-end" onClick={onStop} aria-label="End voice session">
            <PhoneOff size={20} />
          </button>
        </div>
      ) : (
        <div className="start-form">
          <button className="btn btn-primary btn-lg" onClick={start} disabled={voiceReady === false}>
            {state === 'error' ? <><RotateCcw size={16} /> Try again</> : <><Mic size={16} /> Start talking</>}
          </button>
        </div>
      )}
    </section>
  )
}
