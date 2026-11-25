import { useEffect, useRef, useState, type RefObject } from 'react'
import type { Levels, VoiceState } from '../lib/voice'
import { FRAG, VERT } from './orbShader'

interface Props {
  state: VoiceState
  /** Called every frame: live levels and speech bands from the mic and the agent's playback. */
  levels: () => Levels
  /** The element the orb is centred on and sized to (the orb's hit target). */
  anchor: RefObject<HTMLElement | null>
  /** Changes whenever a bank confirms units: plays the green bloom and a green pebble. */
  bloomKey: number
  /** Changes when a session starts: drops a pebble from the orb. */
  pebbleKey: number
}

// [highlight, body, depth] per state
const TONES: Record<VoiceState, [string, string, string]> = {
  idle: ['#b9c3ff', '#7b8ef2', '#434fcf'],
  connecting: ['#9aa6e0', '#4c5cb8', '#1c2260'],
  listening: ['#b3c0ff', '#7488f0', '#3f4bcc'],
  user: ['#e4fbff', '#52cfff', '#1662c9'],
  thinking: ['#e6d9ff', '#9a7bff', '#3a28a6'],
  speaking: ['#e9b2e4', '#8a7cf0', '#3442c4'],
  error: ['#ffd0d0', '#ff6b6b', '#7a1f2c'],
}
// second hue per state: drifting blobs inside the orb and the far stage glow
const ACCENT: Record<VoiceState, string> = {
  idle: '#cf86ee',
  connecting: '#6f7bd0',
  listening: '#b48cf5',
  user: '#5ef0d6',
  thinking: '#c98bff',
  speaking: '#ff86d3',
  error: '#ff9a7a',
}
const PEBBLE_MS = 1900
const BLOOM_MS = 1700

const rgb = (hex: string): number[] => {
  const n = parseInt(hex.slice(1), 16)
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
}

/** Full-stage WebGL canvas: aurora fog + the voice orb. Falls back to a CSS orb without WebGL. */
export function Orb({ state, levels, anchor, bloomKey, pebbleKey }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef(state)
  stateRef.current = state
  const bloomAt = useRef(-1e9)
  const pebble = useRef({ at: -1e9, green: false })
  const [fallback, setFallback] = useState(false)

  useEffect(() => {
    if (!bloomKey) return
    bloomAt.current = performance.now()
    pebble.current = { at: performance.now(), green: true }
  }, [bloomKey])
  useEffect(() => { if (pebbleKey) pebble.current = { at: performance.now(), green: false } }, [pebbleKey])

  useEffect(() => {
    const canvas = ref.current!
    const gl = canvas.getContext('webgl', { antialias: false, alpha: true, premultipliedAlpha: true })
    if (!gl || gl.isContextLost()) { setFallback(true); return }

    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!
      gl.shaderSource(s, src)
      gl.compileShader(s)
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? 'shader')
      return s
    }
    let prog: WebGLProgram
    try {
      prog = gl.createProgram()!
      gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT))
      gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG))
      gl.linkProgram(prog)
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) ?? 'link')
    } catch (e) {
      console.warn('orb shader failed, using fallback', e)
      setFallback(true)
      return
    }
    gl.useProgram(prog)
    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    const loc = gl.getAttribLocation(prog, 'aPos')
    gl.enableVertexAttribArray(loc)
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
    const U = (n: string) => gl.getUniformLocation(prog, n)
    const u = {
      center: U('uCenter'), radius: U('uRadius'), time: U('uTime'), c1: U('uC1'), c2: U('uC2'), c3: U('uC3'),
      bg: U('uBg'), amp: U('uAmp'), low: U('uLow'), mid: U('uMid'), high: U('uHigh'), glow: U('uGlow'),
      ripple: U('uRipple'), shimmer: U('uShimmer'), arc: U('uArc'), bloom: U('uBloom'),
      accent: U('uAccent'), pebble: U('uPebble'), pebbleCol: U('uPebbleCol'),
    }

    // Resolution adapts to the machine: start sharp, and step down if frames take too long. The shader is
    // per-pixel, so fewer pixels is the cheapest way to keep the voice UI smooth on older laptops and phones.
    let dpr = Math.min(window.devicePixelRatio || 1, 1.75)
    const MIN_DPR = 0.7
    let slowMs = 0
    let slowFrames = 0
    const resize = () => {
      const w = Math.max(1, Math.round(canvas.clientWidth * dpr))
      const h = Math.max(1, Math.round(canvas.clientHeight * dpr))
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; gl.viewport(0, 0, w, h) }
    }
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)
    resize()

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)')
    const cols = TONES[stateRef.current].map(rgb)
    const acc = rgb(ACCENT[stateRef.current])
    const sm = { amp: 0, low: 0, mid: 0, high: 0, glow: 0.3, ripple: 0, shimmer: 0, arc: 0, scale: 0.9 }
    let t = 0
    let last = performance.now()
    let raf = 0

    const ease = (cur: number, target: number, attack: number, release: number) =>
      cur + (target - cur) * (target > cur ? attack : release)

    const frame = (now: number) => {
      const raw = now - last
      const dt = Math.min(0.05, raw / 1000)
      last = now
      // frame-time watchdog: ~1.5 s of frames averaging over 26 ms (under ~38 fps) lowers the resolution one step
      if (raw < 250) {
        slowMs += raw
        slowFrames += 1
        if (slowFrames >= 60) {
          if (slowMs / slowFrames > 26 && dpr > MIN_DPR) { dpr = Math.max(MIN_DPR, dpr * 0.78); resize() }
          slowMs = 0
          slowFrames = 0
        }
      }
      const still = reduce.matches
      if (!still) t += dt
      const s = stateRef.current
      const L = levels()

      // whose voice drives the orb right now
      const src = s === 'speaking' ? { a: L.out, b: L.outBands } : s === 'user' || s === 'listening' ? { a: L.mic, b: L.micBands } : null
      const gain = s === 'listening' ? 0.35 : 1
      const tgt = still || !src ? { a: 0, b: [0, 0, 0] } : { a: src.a * gain, b: src.b.map((x) => x * gain) }
      sm.amp = ease(sm.amp, tgt.a, 0.07, 0.035) // slow envelope: breathe, never flicker
      sm.low = ease(sm.low, tgt.b[0], 0.06, 0.03)
      sm.mid = ease(sm.mid, tgt.b[1], 0.05, 0.025)
      sm.high = ease(sm.high, tgt.b[2], 0.05, 0.025)

      const k = 1 - Math.exp(-dt / 0.22) // state morph rate
      const glowT = s === 'idle' ? 0.45 : s === 'error' ? 0.35 : s === 'connecting' ? 0.35 : 0.5 + sm.amp * 0.15
      sm.glow += (glowT - sm.glow) * k
      sm.ripple = ease(sm.ripple, s === 'user' && !still ? Math.min(1, L.mic * 2.2) : 0, 0.3, 0.16)
      sm.shimmer += ((s === 'thinking' ? 1 : 0) - sm.shimmer) * k
      sm.arc += ((s === 'connecting' ? 1 : 0) - sm.arc) * k
      // the anchor is the max size; leave headroom for the voice swell and edge wobble
      const scaleT = s === 'user' ? 0.86 : s === 'speaking' ? 0.9 : s === 'idle' ? 0.82 : s === 'connecting' ? 0.8 : 0.86
      sm.scale += (scaleT - sm.scale) * k
      const at = rgb(ACCENT[s])
      for (let j = 0; j < 3; j++) acc[j] += (at[j] - acc[j]) * k
      TONES[s].forEach((hex, i) => {
        const c = rgb(hex)
        for (let j = 0; j < 3; j++) cols[i][j] += (c[j] - cols[i][j]) * k
      })

      // centre and size from the anchor element
      const a = anchor.current?.getBoundingClientRect()
      const c = canvas.getBoundingClientRect()
      const cx = a ? (a.left + a.width / 2 - c.left) * dpr : canvas.width / 2
      const cy = a ? (c.bottom - (a.top + a.height / 2)) * dpr : canvas.height / 2
      const base = a ? (a.width / 2) * dpr : 150 * dpr
      const live = s === 'speaking' ? Math.min(sm.amp, 0.8) * 0.07 : s === 'user' ? Math.min(sm.amp, 0.8) * 0.045 : 0

      const bloom = Math.max(0, 1 - (now - bloomAt.current) / BLOOM_MS)

      gl.uniform2f(u.center, cx, cy)
      gl.uniform1f(u.radius, base * (sm.scale + live))
      gl.uniform1f(u.time, still ? 12.0 : t)
      gl.uniform3fv(u.c1, cols[0])
      gl.uniform3fv(u.c2, cols[1])
      gl.uniform3fv(u.c3, cols[2])
      gl.uniform1f(u.amp, sm.amp)
      gl.uniform1f(u.low, sm.low)
      gl.uniform1f(u.mid, sm.mid)
      gl.uniform1f(u.high, sm.high)
      gl.uniform1f(u.glow, sm.glow)
      gl.uniform1f(u.ripple, sm.ripple)
      gl.uniform1f(u.shimmer, sm.shimmer)
      gl.uniform1f(u.arc, sm.arc)
      gl.uniform1f(u.bloom, still ? 0 : bloom)
      gl.uniform3fv(u.accent, acc)
      const pp = (now - pebble.current.at) / PEBBLE_MS
      // ease-out so rings leave fast and settle slowly, like water
      gl.uniform1f(u.pebble, still || pp >= 1 ? 1 : 1 - Math.pow(1 - pp, 2.2))
      gl.uniform3fv(u.pebbleCol, pebble.current.green ? [0.29, 0.87, 0.5] : cols[0])
      gl.drawArrays(gl.TRIANGLES, 0, 3)
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    // no loseContext() here: a remount (StrictMode, HMR) gets the same canvas context back
    return () => { cancelAnimationFrame(raf); ro.disconnect(); gl.deleteProgram(prog); gl.deleteBuffer(buf) }
  }, [levels, anchor])

  // no WebGL: the anchor itself becomes a CSS orb
  useEffect(() => {
    const el = anchor.current
    if (!el) return
    el.classList.toggle('orb-css', fallback)
    el.dataset.state = state
  }, [fallback, state, anchor])

  if (fallback) return null
  return <canvas ref={ref} className="stage-canvas" aria-hidden="true" />
}
