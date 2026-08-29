import type { ConnectionState, VisualIntent } from '@glia/api-client'
import { create } from 'zustand'

/** Where the browser's microphone permission currently stands. */
export type MicState = 'idle' | 'requesting' | 'granted' | 'denied' | 'unsupported'

/**
 * What the screen is showing. Deliberately separate from `MicState`: permission is a device
 * concern, phase is a product one, and a session that has started stays started whether or not
 * the microphone is currently open.
 */
export type SessionPhase = 'hero' | 'session'

interface SessionState {
  micState: MicState
  /** The live capture stream while `micState` is `granted`, and null in every other state. */
  stream: MediaStream | null
  phase: SessionPhase
  /** State and stream move together — a granted state without a stream is not representable. */
  setMic: (micState: MicState, stream: MediaStream | null) => void
  /**
   * Speech has arrived. One-way: stopping the microphone stops listening but must never throw the
   * user back to an empty hero, because by then there is a transcript on screen to destroy.
   */
  startSession: () => void
  connectionState: ConnectionState
  connectionError: string | null
  transcript: string
  intent: VisualIntent | null
  setConnection: (connectionState: ConnectionState, connectionError?: string | null) => void
  setTranscript: (transcript: string) => void
  setIntent: (intent: VisualIntent, transcript: string) => void
  resetRealtime: () => void
}

/**
 * Words on screen mean the session has begun, whichever signal noticed first. The level detector
 * is the fast path — it trips about 250ms into the first sentence, well before any text arrives —
 * but it is not the only one: when the realtime provider is unconfigured the transcript comes from
 * a fixture that nobody had to speak for, and a transcript with no layout to land in is invisible.
 */
function phaseAfter(state: SessionState, transcript: string): SessionPhase {
  return state.phase === 'hero' && transcript.trim() ? 'session' : state.phase
}

export const useSessionStore = create<SessionState>()((set) => ({
  micState: 'idle',
  stream: null,
  phase: 'hero',
  setMic: (micState, stream) => set({ micState, stream }),
  startSession: () => set((state) => (state.phase === 'hero' ? { phase: 'session' } : state)),
  connectionState: 'idle',
  connectionError: null,
  transcript: '',
  intent: null,
  setConnection: (connectionState, connectionError = null) =>
    set({ connectionState, connectionError }),
  setTranscript: (transcript) =>
    set((state) => ({ transcript, phase: phaseAfter(state, transcript) })),
  setIntent: (intent, transcript) =>
    set((state) => ({ intent, transcript, phase: phaseAfter(state, transcript) })),
  resetRealtime: () =>
    set({ connectionState: 'idle', connectionError: null, transcript: '', intent: null }),
}))
