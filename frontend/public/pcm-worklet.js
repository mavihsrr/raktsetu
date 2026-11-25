// Mic -> 16 kHz mono PCM16, posted in 20 ms frames (320 samples).
// A one-pole low-pass before decimation keeps aliasing out of the speech band.
class Pcm16Downsampler extends AudioWorkletProcessor {
  constructor() {
    super()
    this.ratio = sampleRate / 16000
    this.pos = 0
    this.lp = 0
    this.alpha = 1 - Math.exp((-2 * Math.PI * 7000) / sampleRate)
    this.frame = new Int16Array(320)
    this.n = 0
    this.filtered = new Float32Array(128)
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (!ch) return true
    if (this.filtered.length < ch.length) this.filtered = new Float32Array(ch.length)
    for (let i = 0; i < ch.length; i++) {
      this.lp += this.alpha * (ch[i] - this.lp)
      this.filtered[i] = this.lp
    }
    while (this.pos < ch.length) {
      const s = Math.max(-1, Math.min(1, this.filtered[Math.floor(this.pos)]))
      this.frame[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff
      if (this.n === this.frame.length) {
        this.port.postMessage(this.frame.buffer.slice(0))
        this.n = 0
      }
      this.pos += this.ratio
    }
    this.pos -= ch.length
    return true
  }
}

registerProcessor('pcm16-downsampler', Pcm16Downsampler)
