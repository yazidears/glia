import { create } from 'zustand'

/** Where the browser's microphone permission currently stands. */
export type MicState = 'idle' | 'requesting' | 'granted' | 'denied' | 'unsupported'

interface SessionState {
  micState: MicState
  /** The live capture stream while `micState` is `granted`, and null in every other state. */
  stream: MediaStream | null
  /** State and stream move together — a granted state without a stream is not representable. */
  setMic: (micState: MicState, stream: MediaStream | null) => void
}

export const useSessionStore = create<SessionState>()((set) => ({
  micState: 'idle',
  stream: null,
  setMic: (micState, stream) => set({ micState, stream }),
}))
