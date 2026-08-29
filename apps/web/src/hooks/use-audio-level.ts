import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useSessionStore } from '@/stores/session'

/**
 * 1024 samples is ~21ms at 48kHz: long enough for a stable level, short enough that the bars
 * react to a syllable rather than to a sentence. Smoothing is the analyser's own, so the level
 * decays instead of strobing between frames.
 */
const FFT_SIZE = 1024
const SMOOTHING_TIME_CONSTANT = 0.8

/**
 * Hysteresis band for "someone is talking". Crossing into speech needs a clearly voiced level;
 * falling out of it only needs a much quieter one, so a keyboard click or a chair creak cannot
 * ratchet the sustain timer forward one frame at a time.
 */
const VOICE_ENTER_RMS = 0.03
const VOICE_EXIT_RMS = 0.012
const VOICE_SUSTAIN_MS = 250

type AnalyserListener = (analyser: AnalyserNode | null) => void

export interface AudioLevelHandle {
  getAnalyser: () => AnalyserNode | null
  /** Calls `listener` immediately with the current analyser, then again on every change. */
  subscribe: (listener: AnalyserListener) => () => void
}

/**
 * There is one microphone per document, so there is one AudioContext, and it lives outside React.
 * It has to be constructed while a user gesture is on the call stack — that is the browser's
 * autoplay policy — and that is a different call stack from the effect that later receives the
 * stream, so a ref inside a component cannot own it.
 */
let sharedContext: AudioContext | null = null

/**
 * Call this synchronously from a click handler. It creates the context on the first click and
 * resumes it on every later one, which is what keeps a context that the browser suspended in the
 * background from silently drawing a flat line forever.
 */
export function primeAudioContext(): AudioContext | null {
  if (typeof AudioContext === 'undefined') {
    return null
  }

  const context = sharedContext ?? new AudioContext()
  sharedContext = context

  if (context.state === 'suspended') {
    // A rejected resume is not fatal and not swallowed: the next click primes the context again,
    // which is the only place the policy will let it start anyway.
    context.resume().catch(() => undefined)
  }

  return context
}

/**
 * Releases the audio hardware. Owned by the microphone lifecycle rather than by a component
 * effect, because the context must survive React's development-mode double mount and must not
 * survive the stream it was opened for.
 */
export async function closeAudioContext(): Promise<void> {
  const context = sharedContext
  sharedContext = null

  if (context && context.state !== 'closed') {
    await context.close()
  }
}

/**
 * Builds `MediaStream -> MediaStreamAudioSourceNode -> AnalyserNode` for the session's stream and
 * hands the analyser out by subscription.
 *
 * Per-frame values never reach React or Zustand. A 60fps `setState` would rerender the whole
 * screen sixty times a second; consumers read the analyser directly inside their own animation
 * frame instead. The detector remains a fallback for restored or externally supplied streams;
 * the normal permission flow moves into the session as soon as the microphone is granted.
 */
export function useAudioLevel(): AudioLevelHandle {
  const stream = useSessionStore((state) => state.stream)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const listenersRef = useRef<Set<AnalyserListener>>(new Set())

  const publish = useCallback((analyser: AnalyserNode | null): void => {
    analyserRef.current = analyser
    for (const listener of listenersRef.current) {
      listener(analyser)
    }
  }, [])

  const subscribe = useCallback((listener: AnalyserListener): (() => void) => {
    const listeners = listenersRef.current
    listeners.add(listener)
    listener(analyserRef.current)
    return () => {
      listeners.delete(listener)
    }
  }, [])

  useEffect(() => {
    if (!stream) {
      return
    }

    const context = primeAudioContext()
    if (!context) {
      return
    }

    const source = context.createMediaStreamSource(stream)
    const analyser = context.createAnalyser()
    const silentSink = context.createGain()
    analyser.fftSize = FFT_SIZE
    analyser.smoothingTimeConstant = SMOOTHING_TIME_CONSTANT
    // Safari may stop pulling an unconnected Web Audio graph. Keep it live through a zero-gain
    // sink: the analyser receives real samples, while no microphone audio reaches the speakers.
    silentSink.gain.value = 0
    source.connect(analyser)
    analyser.connect(silentSink)
    silentSink.connect(context.destination)
    publish(analyser)

    // Safari suspends Web Audio when a tab spends time in the background, even though the
    // MediaStream track can remain live. Resume the already-authorised context when Glia becomes
    // visible again so the button cannot say Listening while its analyser is frozen.
    const resumeWhenVisible = (): void => {
      if (
        document.visibilityState === 'visible' &&
        context.state !== 'running' &&
        context.state !== 'closed'
      ) {
        void context.resume().catch(() => undefined)
      }
    }
    document.addEventListener('visibilitychange', resumeWhenVisible)
    window.addEventListener('pageshow', resumeWhenVisible)

    let frame: number | null = null

    // Detection runs in the analyser loop, not in React, and only while the session is still on
    // the hero. Once the phase has moved there is nothing left to detect.
    if (useSessionStore.getState().phase === 'hero') {
      const samples = new Float32Array(analyser.fftSize)
      let voicedSince: number | null = null

      const detect = (now: number): void => {
        analyser.getFloatTimeDomainData(samples)

        let sumOfSquares = 0
        for (let index = 0; index < samples.length; index += 1) {
          const sample = samples[index] ?? 0
          sumOfSquares += sample * sample
        }
        const rms = Math.sqrt(sumOfSquares / samples.length)

        if (voicedSince === null) {
          if (rms >= VOICE_ENTER_RMS) {
            voicedSince = now
          }
        } else if (rms < VOICE_EXIT_RMS) {
          voicedSince = null
        } else if (now - voicedSince >= VOICE_SUSTAIN_MS) {
          useSessionStore.getState().startSession()
          // Fires once per session: the loop is not rescheduled and the phase is one-way.
          frame = null
          return
        }

        frame = requestAnimationFrame(detect)
      }

      frame = requestAnimationFrame(detect)
    }

    return () => {
      if (frame !== null) {
        cancelAnimationFrame(frame)
      }
      publish(null)
      document.removeEventListener('visibilitychange', resumeWhenVisible)
      window.removeEventListener('pageshow', resumeWhenVisible)
      source.disconnect()
      analyser.disconnect()
      silentSink.disconnect()
    }
  }, [stream, publish])

  return useMemo(() => ({ getAnalyser: () => analyserRef.current, subscribe }), [subscribe])
}
