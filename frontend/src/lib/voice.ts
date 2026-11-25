import { voiceSocketUrl } from './api'

/**
 * idle       no session
 * connecting opening mic + Sarvam session (takes several seconds)
 * listening  connected, waiting for the user
 * user       the user is speaking (server VAD)
 * thinking   user finished, agent has not started speaking yet
 * speaking   agent audio is playing
 */
export type VoiceState = 'idle' | 'connecting' | 'listening' | 'user' | 'thinking' | 'speaking' | 'error'

export type Bands = [low: number, mid: number, high: number]
export interface Levels { mic: number; out: number; micBands: Bands; outBands: Bands }

export interface VoiceLine { id: string; role: 'user' | 'agent'; text: string; ts: number }

interface Handlers {
  onState: (s: VoiceState, detail?: string) => void
  onLine: (l: VoiceLine) => void
}

let lineSeq = 0

export class VoiceSession {
  private ws: WebSocket | null = null
  private ctx: AudioContext | null = null
  private mic: MediaStream | null = null
  private micAnalyser: AnalyserNode | null = null
  private outAnalyser: AnalyserNode | null = null
  private outGain: GainNode | null = null
  private playHead = 0
  private sources = new Set<AudioBufferSourceNode>()
  private state: VoiceState = 'idle'
  private buf = new Float32Array(1024)
  private closedByUser = false
  muted = false

  private h: Handlers

  constructor(h: Handlers) {
    this.h = h
  }

  get current() { return this.state }

  private set(s: VoiceState, detail?: string) {
    this.state = s
    this.h.onState(s, detail)
  }

  async start(opts: { name: string; hospital: string; language: string }) {
    this.closedByUser = false
    this.set('connecting')
    try {
      this.mic = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      })
    } catch {
      this.set('error', 'The microphone is blocked. Allow it in the browser, or type the request in Live status.')
      return
    }
    const ctx = new AudioContext()
    this.ctx = ctx
    try {
      await ctx.resume() // Safari can create it suspended after the mic prompt
      await ctx.audioWorklet.addModule(`${import.meta.env.BASE_URL}pcm-worklet.js`)
    } catch {
      this.set('error', 'Could not start audio in this browser. Reload the page and try again.')
      this.teardown()
      return
    }

    const src = ctx.createMediaStreamSource(this.mic)
    this.micAnalyser = ctx.createAnalyser()
    this.micAnalyser.fftSize = 1024
    this.micAnalyser.minDecibels = -85
    this.micAnalyser.maxDecibels = -25
    this.micAnalyser.smoothingTimeConstant = 0.6
    src.connect(this.micAnalyser)

    const worklet = new AudioWorkletNode(ctx, 'pcm16-downsampler')
    src.connect(worklet)
    const sink = ctx.createGain()
    sink.gain.value = 0
    worklet.connect(sink).connect(ctx.destination) // keeps the worklet pulled, silently
    const silence = new ArrayBuffer(640) // 20 ms of 16 kHz PCM16
    worklet.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(this.muted ? silence : e.data)
    }

    this.outGain = ctx.createGain()
    this.outAnalyser = ctx.createAnalyser()
    this.outAnalyser.fftSize = 1024
    this.outAnalyser.minDecibels = -85
    this.outAnalyser.maxDecibels = -25
    this.outAnalyser.smoothingTimeConstant = 0.6
    this.outGain.connect(this.outAnalyser).connect(ctx.destination)

    const ws = new WebSocket(voiceSocketUrl())
    ws.binaryType = 'arraybuffer'
    this.ws = ws
    ws.onopen = () => ws.send(JSON.stringify({ type: 'start', ...opts }))
    ws.onmessage = (e) => (typeof e.data === 'string' ? this.onJson(e.data) : this.onAudio(e.data as ArrayBuffer))
    ws.onerror = () => { if (this.state === 'connecting') this.set('error', 'Could not reach the voice server.') }
    ws.onclose = (e) => {
      if (this.state === 'connecting' && !this.closedByUser) {
        this.set('error',
          e.code === 4401 ? 'Access token missing or invalid. Open the link with #token=… from your team.'
          : e.code === 4403 ? 'Voice is not allowed from this address.'
          : 'The voice server closed the session. Try again.')
      } else if (this.state !== 'error') {
        this.set('idle')
      }
      this.teardown()
    }
  }

  private onJson(raw: string) {
    let m: { type: string; [k: string]: unknown }
    try { m = JSON.parse(raw) } catch { return }
    switch (m.type) {
      case 'state':
        if (m.state === 'connected') this.set('listening')
        else if (m.state === 'error') this.set('error', String(m.detail ?? 'Voice session failed.'))
        else if (m.state === 'ended' && !this.closedByUser && this.state !== 'error') this.set('idle')
        break
      case 'greeting':
      case 'transcript': {
        const role = m.type === 'greeting' ? 'agent' : (m.role as 'user' | 'agent')
        const text = String(m.text ?? '').trim()
        if (text) this.h.onLine({ id: `v${++lineSeq}`, role, text, ts: Date.now() / 1000 })
        break
      }
      case 'speech':
        if (m.phase === 'start') this.set('user')
        else if (this.state === 'user') this.set('thinking')
        break
      case 'interrupt':
        this.stopPlayback()
        break
    }
  }

  private onAudio(data: ArrayBuffer) {
    const ctx = this.ctx
    if (!ctx || !this.outGain || data.byteLength < 6) return
    const rate = new DataView(data).getUint32(0, true)
    const pcm = new Int16Array(data, 4, (data.byteLength - 4) >> 1)
    const buffer = ctx.createBuffer(1, pcm.length, rate)
    const ch = buffer.getChannelData(0)
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 0x8000
    const node = ctx.createBufferSource()
    node.buffer = buffer
    node.connect(this.outGain)
    const at = Math.max(ctx.currentTime + 0.04, this.playHead)
    node.start(at)
    this.playHead = at + buffer.duration
    this.sources.add(node)
    if (this.state !== 'speaking') this.set('speaking')
    node.onended = () => {
      this.sources.delete(node)
      if (this.sources.size === 0 && this.state === 'speaking') this.set('listening')
    }
  }

  private stopPlayback() {
    for (const s of this.sources) { try { s.stop() } catch { /* already stopped */ } }
    this.sources.clear()
    if (this.ctx) this.playHead = this.ctx.currentTime
  }

  /** Levels 0..1 for the orb, read every animation frame: overall RMS plus low / mid / high speech bands. */
  levels(): Levels {
    const silent: Bands = [0, 0, 0]
    return {
      mic: this.muted ? 0 : this.rms(this.micAnalyser),
      out: this.rms(this.outAnalyser),
      micBands: this.muted ? silent : this.bands(this.micAnalyser),
      outBands: this.bands(this.outAnalyser),
    }
  }

  private freq = new Uint8Array(512)

  // speech bands: body (80-300 Hz), formants (300-1500 Hz), sibilance (1.5-4 kHz)
  private bands(a: AnalyserNode | null): Bands {
    if (!a || !this.ctx) return [0, 0, 0]
    if (this.freq.length !== a.frequencyBinCount) this.freq = new Uint8Array(a.frequencyBinCount)
    a.getByteFrequencyData(this.freq)
    const hz = this.ctx.sampleRate / a.fftSize
    const avg = (lo: number, hi: number) => {
      const i0 = Math.max(1, Math.floor(lo / hz))
      const i1 = Math.min(this.freq.length - 1, Math.ceil(hi / hz))
      let s = 0
      for (let i = i0; i <= i1; i++) s += this.freq[i]
      return s / ((i1 - i0 + 1) * 255)
    }
    return [avg(80, 300), avg(300, 1500), avg(1500, 4000)]
  }

  private rms(a: AnalyserNode | null): number {
    if (!a) return 0
    if (this.buf.length !== a.fftSize) this.buf = new Float32Array(a.fftSize)
    a.getFloatTimeDomainData(this.buf)
    let sum = 0
    for (let i = 0; i < this.buf.length; i++) sum += this.buf[i] * this.buf[i]
    return Math.min(1, Math.sqrt(sum / this.buf.length) * 4)
  }

  stop() {
    this.closedByUser = true
    try { this.ws?.send(JSON.stringify({ type: 'stop' })) } catch { /* closed */ }
    this.ws?.close()
    this.set('idle')
    this.teardown()
  }

  private teardown() {
    this.stopPlayback()
    this.mic?.getTracks().forEach((t) => t.stop())
    this.mic = null
    this.ctx?.close().catch(() => {})
    this.ctx = null
    this.micAnalyser = this.outAnalyser = null
    this.outGain = null
    this.ws = null
  }
}
