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
  private pcs: RTCPeerConnection[] = []
  private audioEl: HTMLAudioElement | null = null
  private agentSpeakingUntil = 0   // ms timestamp: agent audio is playing (or just finished) until then
  private loudFrames = 0
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
      const ws = this.ws
      if (ws?.readyState !== WebSocket.OPEN) return
      if (this.muted) { this.resetBridge(); ws.send(silence); return }
      if (this.gated()) {
        // keep the last ~120 ms so the first word of a barge-in is not lost
        this.ring.push(e.data)
        if (this.ring.length > 6) this.ring.shift()
        this.resetBridge()
        ws.send(silence)
        return
      }
      for (const f of this.ring) ws.send(f)
      this.ring = []
      for (const f of this.bridge(e.data)) ws.send(f)
    }

    this.outGain = ctx.createGain()
    this.outAnalyser = ctx.createAnalyser()
    this.outAnalyser.fftSize = 1024
    this.outAnalyser.minDecibels = -85
    this.outAnalyser.maxDecibels = -25
    this.outAnalyser.smoothingTimeConstant = 0.6
    this.outGain.connect(this.outAnalyser)
    // Echo fix: the browser only cancels audio it can tell is playing. Web Audio output is often NOT
    // cancelled on laptop speakers (the agent then hears itself and talks over you). Audio that arrives
    // over WebRTC is, so loop the agent's voice through a local peer connection into an <audio> element.
    if (!(await this.playViaWebRtc(ctx))) this.outAnalyser.connect(ctx.destination)

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

  private async playViaWebRtc(ctx: AudioContext): Promise<boolean> {
    try {
      const dest = ctx.createMediaStreamDestination()
      this.outAnalyser!.connect(dest)
      const a = new RTCPeerConnection()
      const b = new RTCPeerConnection()
      this.pcs = [a, b]
      a.onicecandidate = (e) => { if (e.candidate) b.addIceCandidate(e.candidate).catch(() => {}) }
      b.onicecandidate = (e) => { if (e.candidate) a.addIceCandidate(e.candidate).catch(() => {}) }
      dest.stream.getTracks().forEach((t) => a.addTrack(t, dest.stream))
      const el = new Audio()
      el.autoplay = true
      this.audioEl = el
      b.ontrack = (e) => { el.srcObject = e.streams[0]; el.play().catch(() => {}) }
      await a.setLocalDescription(await a.createOffer())
      await b.setRemoteDescription(a.localDescription!)
      await b.setLocalDescription(await b.createAnswer())
      await a.setRemoteDescription(b.localDescription!)
      return true
    } catch {
      this.pcs.forEach((p) => p.close())
      this.pcs = []
      return false
    }
  }

  /**
   * While the agent talks, send silence instead of the mic so leftover echo is never taken for you.
   * Your voice (louder than the echo that survives the browser's echo cancellation) for ~60 ms
   * cuts in: playback stops at once and the mic opens.
   */
  private gated(): boolean {
    if (Date.now() > this.agentSpeakingUntil) { this.loudFrames = 0; return false }
    this.loudFrames = this.rms(this.micAnalyser) > 0.18 ? this.loudFrames + 1 : 0
    if (this.loudFrames >= 4) { // ~80 ms of normal speech: barge-in
      this.agentSpeakingUntil = 0
      this.dropAgentUntil = Date.now() + 8000   // the server keeps streaming the rest of the sentence: ignore it
      this.stopPlayback()
      this.set('user')
      return false
    }
    return true
  }

  /**
   * Pause bridge. The agent ends your turn after a short silence, so a breath mid-sentence
   * ("B positive, two units... at KIMS Hubli") made it reply over you. While you are talking,
   * the first 120 ms of a pause is sent as-is and the rest is held back. If you carry on within
   * ~0.8 s the held silence is dropped, so the agent never sees a long gap. If you don't, it is
   * all sent at once and the agent replies.
   */
  private talking = false
  private voiced = 0
  private gap = 0
  private held: ArrayBuffer[] = []
  private floorDb = -60
  private ring: ArrayBuffer[] = []
  private dropAgentUntil = 0   // after a barge-in, ignore the agent's stale audio until it answers you
  private settle: ReturnType<typeof setTimeout> | null = null

  private resetBridge() {
    this.talking = false
    this.voiced = 0
    this.gap = 0
    this.held = []
  }

  private bridge(frame: ArrayBuffer): ArrayBuffer[] {
    const KEEP = 4      // 80 ms of each pause passes through
    const END = 22      // 440 ms of silence = you have finished
    const pcm = new Int16Array(frame)
    let sum = 0
    for (let i = 0; i < pcm.length; i++) sum += pcm[i] * pcm[i]
    const db = 20 * Math.log10(Math.sqrt(sum / pcm.length) / 0x8000 + 1e-9)
    const speech = db > -45 && db > this.floorDb + 9
    if (!speech) this.floorDb += (db - this.floorDb) * (db < this.floorDb ? 0.3 : 0.02) // track room noise

    if (speech) {
      this.voiced++
      if (this.voiced >= 3) this.talking = true
      this.gap = 0
      this.held = []   // you carried on: the pause is dropped
      return [frame]
    }
    this.voiced = 0
    if (!this.talking) return [frame]
    this.gap++
    if (this.gap <= KEEP) return [frame]
    if (this.gap < END) { this.held.push(frame); return [] }
    const out = [...this.held, frame]   // a real end of turn: release the silence now
    this.resetBridge()
    return out
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
        if (m.type === 'transcript' && role === 'user') this.dropAgentUntil = 0   // you were heard: the next audio answers you
        if (text) this.h.onLine({ id: `v${++lineSeq}`, role, text, ts: Date.now() / 1000 })
        break
      }
      case 'speech':
        if (m.phase === 'start') this.set('user')
        else if (this.state === 'user') this.set('thinking')
        break
      case 'interrupt':
        this.stopPlayback()
        this.dropAgentUntil = 0   // the server dropped its queue: what comes next is the real reply
        break
    }
  }

  private onAudio(data: ArrayBuffer) {
    const ctx = this.ctx
    if (!ctx || !this.outGain || data.byteLength < 6) return
    if (Date.now() < this.dropAgentUntil) return
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
    node.onended = () => { this.sources.delete(node) }
    // Only real speech counts as the agent talking. Quiet filler (background ambience measured at
    // -37..-42 dBFS, speech at about -13) must never close your mic, or the agent hears you in pieces.
    let sq = 0
    for (let i = 0; i < ch.length; i++) sq += ch[i] * ch[i]
    if (Math.sqrt(sq / Math.max(1, ch.length)) < 0.025) return   // below ~-32 dBFS
    // short tail only: covers output latency, so your reply right after the agent is not cut off
    this.agentSpeakingUntil = Date.now() + (this.playHead - ctx.currentTime) * 1000 + 120
    if (this.state !== 'speaking') this.set('speaking')
    // back to listening only once the agent has really been quiet for a moment (not between chunks)
    if (this.settle) clearTimeout(this.settle)
    this.settle = setTimeout(() => {
      if (this.state === 'speaking' && Date.now() >= this.agentSpeakingUntil) this.set('listening')
    }, Math.max(0, this.agentSpeakingUntil - Date.now()) + 350)
  }

  private stopPlayback() {
    for (const s of this.sources) { try { s.stop() } catch { /* already stopped */ } }
    this.sources.clear()
    this.agentSpeakingUntil = 0
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
    if (this.settle) clearTimeout(this.settle)
    this.settle = null
    this.ring = []
    this.dropAgentUntil = 0
    this.resetBridge()
    this.mic?.getTracks().forEach((t) => t.stop())
    this.mic = null
    this.pcs.forEach((p) => p.close())
    this.pcs = []
    if (this.audioEl) { this.audioEl.srcObject = null; this.audioEl = null }
    this.ctx?.close().catch(() => {})
    this.ctx = null
    this.micAnalyser = this.outAnalyser = null
    this.outGain = null
    this.ws = null
  }
}
