// Mic -> 16 kHz mono PCM16, posted in 20 ms frames (320 samples).
// Proper anti-aliasing: a 63-tap windowed-sinc low-pass (cut-off 7.2 kHz) runs at the input rate,
// then samples are read at the 16 kHz positions with linear interpolation. The old one-pole filter let
// 8-24 kHz noise fold back into the speech band, which made the speech recogniser mishear.
const TAPS = 63

class Pcm16Downsampler extends AudioWorkletProcessor {
  constructor() {
    super()
    this.ratio = sampleRate / 16000
    this.passthrough = this.ratio <= 1.0001
    const fc = Math.min(7200, 0.45 * 16000) / sampleRate
    const h = new Float32Array(TAPS)
    const M = TAPS - 1
    let sum = 0
    for (let n = 0; n < TAPS; n++) {
      const x = n - M / 2
      const sinc = x === 0 ? 2 * fc : Math.sin(2 * Math.PI * fc * x) / (Math.PI * x)
      const w = 0.42 - 0.5 * Math.cos((2 * Math.PI * n) / M) + 0.08 * Math.cos((4 * Math.PI * n) / M) // Blackman
      h[n] = sinc * w
      sum += h[n]
    }
    for (let n = 0; n < TAPS; n++) h[n] /= sum
    this.h = h
    this.buf = new Float32Array(TAPS - 1 + 256) // history + current block
    this.filtered = new Float32Array(256)
    this.prev = 0 // last filtered sample of the previous block, for interpolation across blocks
    this.pos = 0
    this.frame = new Int16Array(320)
    this.n = 0
  }

  push(s) {
    s = Math.max(-1, Math.min(1, s))
    this.frame[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff
    if (this.n === this.frame.length) {
      this.port.postMessage(this.frame.buffer.slice(0))
      this.n = 0
    }
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (!ch) return true
    const len = ch.length
    if (this.passthrough) {
      for (let i = 0; i < len; i++) this.push(ch[i])
      return true
    }
    const H = TAPS - 1
    if (this.buf.length < H + len) {
      const nb = new Float32Array(H + len)
      nb.set(this.buf.subarray(0, H))
      this.buf = nb
      this.filtered = new Float32Array(len)
    }
    this.buf.set(ch, H)
    const h = this.h
    for (let i = 0; i < len; i++) {
      let acc = 0
      for (let k = 0; k < TAPS; k++) acc += h[k] * this.buf[i + H - k]
      this.filtered[i] = acc
    }
    // read at 16 kHz positions; index -1 is the previous block's last sample
    while (Math.floor(this.pos) + 1 < len) {
      const i = Math.floor(this.pos)
      const frac = this.pos - i
      const a = i < 0 ? this.prev : this.filtered[i]
      const b = this.filtered[i + 1]
      this.push(a + (b - a) * frac)
      this.pos += this.ratio
    }
    this.pos -= len
    this.prev = this.filtered[len - 1]
    this.buf.copyWithin(0, len, len + H) // keep the last TAPS-1 input samples
    return true
  }
}

registerProcessor('pcm16-downsampler', Pcm16Downsampler)
