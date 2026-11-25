import type { Levels, VoiceState } from './voice'

/**
 * Dev-only (`npm run dev`, open /#orbdemo): cycles the orb through every state with synthetic,
 * speech-like levels so the visuals can be tuned without a mic or a Sarvam session.
 * Never part of a production build: App only calls this when import.meta.env.DEV is true.
 */
export function orbDemo(setState: (s: VoiceState) => void, bloom: () => void) {
  const steps: [VoiceState, number][] = [
    ['idle', 2500], ['connecting', 2500], ['listening', 2000], ['user', 4000],
    ['thinking', 3000], ['speaking', 6000], ['listening', 1500],
  ]
  let i = 0
  let state: VoiceState = steps[0][0]
  const timers = new Set<ReturnType<typeof setTimeout>>()
  const later = (fn: () => void, ms: number) => {
    const id = setTimeout(() => { timers.delete(id); fn() }, ms)
    timers.add(id)
  }
  const next = () => {
    state = steps[i][0]
    setState(state)
    if (state === 'speaking') later(bloom, 3000)
    const ms = steps[i][1]
    i = (i + 1) % steps.length
    later(next, ms)
  }
  later(next, 0)

  // syllable-rate envelope (~4-6 Hz) with phrase pauses, like real speech
  const speech = (t: number, seed: number) => {
    const phrase = Math.sin(t * 0.9 + seed) > -0.3 ? 1 : 0.05
    const syl = Math.max(0, Math.sin(t * (9 + seed) ) * 0.6 + Math.sin(t * 13.7 + seed * 2) * 0.4)
    return Math.min(1, phrase * syl * 0.75)
  }
  return {
    stop() { timers.forEach(clearTimeout); timers.clear() },
    levels(): Levels {
      const t = performance.now() / 1000
      const a = speech(t, 1.3)
      const m = speech(t, 0.4)
      return {
        out: state === 'speaking' ? a : 0,
        outBands: state === 'speaking' ? [a * 0.9, a * 0.7, a * 0.45 * (0.5 + 0.5 * Math.sin(t * 23))] : [0, 0, 0],
        mic: state === 'user' ? m : 0,
        micBands: state === 'user' ? [m * 0.8, m * 0.6, m * 0.35] : [0, 0, 0],
      }
    },
  }
}
