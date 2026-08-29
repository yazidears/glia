import { useCallback, useEffect } from 'react'
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

  // Release the device when this screen goes away. Without it a hot reload leaves the browser's
  // recording indicator lit, and an app that looks like it is still listening reads as broken.
  useEffect(() => {
    return () => {
      release(useSessionStore.getState().stream)
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
      setMic('granted', granted)
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
