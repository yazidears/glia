import type { ConnectionState, VisualIntent } from '@glia/api-client'
import { create } from 'zustand'

/** Where the browser's microphone permission currently stands. */
export type MicState = 'idle' | 'requesting' | 'granted' | 'denied' | 'unsupported'

export interface TranscriptSegment {
  itemId: string
  text: string
  complete: boolean
}

interface SessionState {
  micState: MicState
  /** The live capture stream while `micState` is `granted`, and null in every other state. */
  stream: MediaStream | null
  /** State and stream move together — a granted state without a stream is not representable. */
  setMic: (micState: MicState, stream: MediaStream | null) => void
  connectionState: ConnectionState
  connectionError: string | null
  transcript: string
  transcriptSegments: TranscriptSegment[]
  intent: VisualIntent | null
  setConnection: (connectionState: ConnectionState, connectionError?: string | null) => void
  setTranscriptState: (transcript: string, transcriptSegments: TranscriptSegment[]) => void
  setIntent: (intent: VisualIntent) => void
  resetRealtime: () => void
}

export const useSessionStore = create<SessionState>()((set) => ({
  micState: 'idle',
  stream: null,
  setMic: (micState, stream) => set({ micState, stream }),
  connectionState: 'idle',
  connectionError: null,
  transcript: '',
  transcriptSegments: [],
  intent: null,
  setConnection: (connectionState, connectionError = null) =>
    set({ connectionState, connectionError }),
  setTranscriptState: (transcript, transcriptSegments) => set({ transcript, transcriptSegments }),
  setIntent: (intent) => set({ intent }),
  resetRealtime: () =>
    set({
      connectionState: 'idle',
      connectionError: null,
      transcript: '',
      transcriptSegments: [],
      intent: null,
    }),
}))
