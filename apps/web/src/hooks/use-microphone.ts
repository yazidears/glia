import { useCallback, useEffect, useRef } from 'react'
import { closeAudioContext, primeAudioContext } from '@/hooks/use-audio-level'
import { type MicState, useSessionStore } from '@/stores/session'

function stopTracks(stream: MediaStream | null): void {
  if (!stream) {
    return
  }
  for (const track of stream.getTracks()) {
    track.stop()
  }
}

/** Stopping is one act: release the device, then release the audio hardware behind it. */
function release(stream: MediaStream | null): void {
  stopTracks(stream)
  // Nothing waits on the close; a context that has been detached from its stream is already
  // silent, and `state` settles to `closed` on its own.
  void closeAudioContext()
}

/**
 * A track can be ended by Safari, macOS, or a hot reload without going through our toggle.
 * Only clear the store when this is still the active stream so an old callback cannot stop a
 * newer microphone session.
 */
function releaseIfCurrent(stream: MediaStream): void {
  const state = useSessionStore.getState()
  if (state.stream !== stream) {
    return
  }

  release(stream)
  state.setMic('idle', null)
}

/**
 * `NotAllowedError` is a refusal the user can reverse, so it stays actionable. `NotFoundError`
 * means there is no capture device at all, which no amount of clicking will fix — that, and any
 * failure we do not recognise, is reported as `unsupported` rather than blamed on the user.
 */
function classifyFailure(error: unknown): MicState {
  const name = error instanceof DOMException ? error.name : ''
  return name === 'NotAllowedError' || name === 'PermissionDeniedError' ? 'denied' : 'unsupported'
}

/**
 * Owns the microphone permission lifecycle. Calling `toggle` while idle or denied runs
 * `getUserMedia`, which is what raises the browser's native permission prompt; calling it while
 * granted releases the device again.
 */
export function useMicrophone(): { micState: MicState; toggle: () => void } {
  const micState = useSessionStore((state) => state.micState)
  const setMic = useSessionStore((state) => state.setMic)
  const mounted = useRef(true)

  // Release the device when this screen goes away. Without it a hot reload leaves the browser's
  // recording indicator lit, and an app that looks like it is still listening reads as broken.
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      const state = useSessionStore.getState()
      release(state.stream)
      // Keep the store truthful. HMR used to leave `micState = granted` with an ended track,
      // which rendered a Listening button and a completely flat waveform.
      if (state.stream || state.micState === 'granted' || state.micState === 'requesting') {
        state.setMic('idle', null)
      }
    }
  }, [])

  const request = useCallback(async (): Promise<void> => {
    const { micState: current, stream: activeStream } = useSessionStore.getState()

    if (current === 'requesting') {
      return
    }

    if (current === 'granted') {
      release(activeStream)
      setMic('idle', null)
      return
    }

    // `navigator.mediaDevices` only exists in a secure context: the page must be served over
    // HTTPS or from localhost. On any other origin it is undefined and no prompt is possible.
    const mediaDevices: MediaDevices | undefined = navigator.mediaDevices
    if (!mediaDevices || typeof mediaDevices.getUserMedia !== 'function') {
      release(null)
      setMic('unsupported', null)
      return
    }

    setMic('requesting', null)
    try {
      const granted = await mediaDevices.getUserMedia({ audio: true })

      // The component may have been replaced while Safari's permission prompt was open.
      if (!mounted.current) {
        release(granted)
        return
      }

      const audioTracks = granted.getAudioTracks()
      if (audioTracks.length === 0) {
        release(granted)
        setMic('unsupported', null)
        return
      }

      for (const track of audioTracks) {
        track.addEventListener('ended', () => releaseIfCurrent(granted), { once: true })
      }

      setMic('granted', granted)
      // Permission is the product transition: once the microphone is live, reveal the transcript
      // workspace immediately so the user sees the empty "Speak now." state before speaking.
      useSessionStore.getState().startSession()
    } catch (error) {
      // The context was primed by the click that led here; nothing will ever feed it now.
      release(null)
      setMic(classifyFailure(error), null)
    }
  }, [setMic])

  const toggle = useCallback((): void => {
    // The AudioContext has to be constructed while the click is still on the call stack — after
    // the `getUserMedia` await, the gesture is gone and the browser starts it suspended.
    if (useSessionStore.getState().micState !== 'granted') {
      primeAudioContext()
    }
    void request()
  }, [request])

  return { micState, toggle }
}
