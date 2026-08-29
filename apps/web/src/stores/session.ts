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

/**
 * One pinned reference, in the shape the whole app agrees on.
 *
 * Two image URLs, because display and conditioning are two different jobs. `imageUrl` is what
 * this app renders — for a grid tile that is the backend's `/api/image` proxy, which is exactly
 * why it is useless for generation: fal fetches over the internet and cannot reach localhost.
 * `originImageUrl` is the file on the origin host, and it is the only one the server turns into
 * a reference image.
 *
 * Both are nullable and both are load-bearing. The board's stickers are inline SVG with no URL
 * at all, so they pin as null twice over — which is why there is one pin path and not two: the
 * difference between a pin that conditions the image and a pin that only steers the prompt is a
 * value, not a type.
 */
export interface PinnedRef {
  id: string
  title: string
  lane: string
  imageUrl: string | null
  originImageUrl: string | null
  sourceUrl: string | null
}

/** What the workpane has to show for the generated image. */
export interface GeneratedImage {
  imageUrl: string
  /** Verbatim, exactly what the server sent to fal. Shown, never paraphrased. */
  prompt: string
  model: string
  referenceCount: number
  /**
   * Ids of pins that did not condition the image, because the server could not fetch or
   * re-host them. A dropped pin never fails the generation, so this list is the only way the
   * user finds out — and it is shown rather than swallowed for exactly that reason.
   */
  unavailableReferences: string[]
}

export interface GenerationFailure {
  message: string
  correlationId: string
}

export type GenerationStatus = 'idle' | 'generating' | 'ready' | 'error'

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
  /** The conditioning input, in click order. Empty means the rail is not on screen at all. */
  pinned: PinnedRef[]
  togglePin: (ref: PinnedRef) => void
  clearPins: () => void
  generationStatus: GenerationStatus
  generation: GeneratedImage | null
  generationError: GenerationFailure | null
  startGenerating: () => void
  settleGeneration: (generation: GeneratedImage) => void
  failGeneration: (failure: GenerationFailure) => void
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
  pinned: [],
  generationStatus: 'idle',
  generation: null,
  generationError: null,
  togglePin: (ref) =>
    set((state) => ({
      pinned: state.pinned.some((pin) => pin.id === ref.id)
        ? state.pinned.filter((pin) => pin.id !== ref.id)
        : [...state.pinned, ref],
    })),
  clearPins: () => set({ pinned: [] }),
  // The previous result stays on screen while the next one runs. The rail is the only place
  // that says "generating", so the workpane never blanks out the image the user is comparing
  // against — and the board stays reachable, which is where the next pin comes from.
  startGenerating: () => set({ generationStatus: 'generating', generationError: null }),
  settleGeneration: (generation) =>
    set({ generationStatus: 'ready', generation, generationError: null }),
  failGeneration: (generationError) => set({ generationStatus: 'error', generationError }),
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
      pinned: [],
      generationStatus: 'idle',
      generation: null,
      generationError: null,
    }),
}))
