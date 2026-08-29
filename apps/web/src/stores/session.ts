import type { ConnectionState, VisualIntent } from '@glia/api-client'
import { create } from 'zustand'

/** Where the browser's microphone permission currently stands. */
export type MicState = 'idle' | 'requesting' | 'granted' | 'denied' | 'unsupported'

interface SessionState {
  micState: MicState
  /** The live capture stream while `micState` is `granted`, and null in every other state. */
  stream: MediaStream | null
  /** State and stream move together — a granted state without a stream is not representable. */
  setMic: (micState: MicState, stream: MediaStream | null) => void
  connectionState: ConnectionState
  connectionError: string | null
  transcript: string
  intent: VisualIntent | null
  setConnection: (connectionState: ConnectionState, connectionError?: string | null) => void
  setTranscript: (transcript: string) => void
  setIntent: (intent: VisualIntent, transcript: string) => void
  resetRealtime: () => void
}

export const useSessionStore = create<SessionState>()((set) => ({
  micState: 'idle',
  stream: null,
  setMic: (micState, stream) => set({ micState, stream }),
  connectionState: 'idle',
  connectionError: null,
  transcript: '',
  intent: null,
  setConnection: (connectionState, connectionError = null) =>
    set({ connectionState, connectionError }),
  setTranscript: (transcript) => set({ transcript }),
  setIntent: (intent, transcript) => set({ intent, transcript }),
  resetRealtime: () =>
    set({ connectionState: 'idle', connectionError: null, transcript: '', intent: null }),
}))
