import type { ConnectionState, VisualIntent } from '@glia/api-client'
import { create } from 'zustand'

/** Where the browser's microphone permission currently stands. */
export type MicState = 'idle' | 'requesting' | 'granted' | 'denied' | 'unsupported'

export interface TranscriptSegment {
  itemId: string
  text: string
  complete: boolean
}

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
   * The microphone has activated. One-way: stopping it must never throw the user back to the hero,
   * because the transcript workspace is now the active surface even before the first word arrives.
   */
  startSession: () => void
  connectionState: ConnectionState
  connectionError: string | null
  transcript: string
  transcriptSegments: TranscriptSegment[]
  processedWordCount: number
  intent: VisualIntent | null
  /** The backend's id for this socket, from `session.ready`. Discovery is debounced per session. */
  sessionId: string | null
  /**
   * The transcript as of the last turn the distiller gate approved for discovery, and the only
   * thing discovery is allowed to read. Interim deltas move `transcript` many times a second
   * and must never spend a credit, so they leave this field alone — which makes "unchanged",
   * "not settled" and "the idea did not move" the same no-op for anything keyed on it.
   */
  discoveryTranscript: string
  setConnection: (connectionState: ConnectionState, connectionError?: string | null) => void
  setSessionId: (sessionId: string) => void
  setTranscriptState: (transcript: string, transcriptSegments: TranscriptSegment[]) => void
  setProcessedWordCount: (processedWordCount: number) => void
  /**
   * `shouldDiscover` is the distiller's gate decision, not ours. The backend only evaluates it
   * on a settled turn, so a true here already means "the idea moved enough to be worth a
   * credit" — which is exactly the condition discovery is allowed to fire on.
   */
  setIntent: (intent: VisualIntent, transcript: string, shouldDiscover: boolean) => void
  resetRealtime: () => void
}

/**
 * Words on screen also mean the session has begun. Microphone permission is the primary path, but
 * a transcript may still arrive from a fixture or restored provider state without a live stream;
 * that text must never remain hidden behind the hero.
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
  transcriptSegments: [],
  processedWordCount: 0,
  intent: null,
  sessionId: null,
  discoveryTranscript: '',
  setConnection: (connectionState, connectionError = null) =>
    set({ connectionState, connectionError }),
  setSessionId: (sessionId) => set({ sessionId }),
  setTranscriptState: (transcript, transcriptSegments) =>
    set((state) => ({
      transcript,
      transcriptSegments,
      phase: phaseAfter(state, transcript),
    })),
  setProcessedWordCount: (processedWordCount) =>
    set((state) => ({
      processedWordCount: Math.max(state.processedWordCount, processedWordCount),
    })),
  setIntent: (intent, transcript, shouldDiscover) =>
    set((state) => ({
      intent,
      discoveryTranscript: shouldDiscover ? transcript : state.discoveryTranscript,
    })),
  resetRealtime: () =>
    set({
      connectionState: 'idle',
      connectionError: null,
      transcript: '',
      transcriptSegments: [],
      processedWordCount: 0,
      intent: null,
      sessionId: null,
      discoveryTranscript: '',
    }),
}))
