import type { GenerateRequest, GenerateResponse, PinnedRefPayload } from '@glia/api-client'
import { useCallback } from 'react'
import { voiceCommandFor } from '@/lib/voice-commands'
import {
  type GenerationStatus,
  type PinnedRef,
  type TranscriptSegment,
  useSessionStore,
} from '@/stores/session'

// The server caps its own poll at ~45s and answers with a typed timeout rather than hanging.
// This has to outlast that, or the browser abandons a generation the account has already paid
// for and shows a network error in place of the server's honest one.
const REQUEST_TIMEOUT_MS = 75_000

function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  return `${base}${path}`
}

/**
 * The one place the store's camelCase pin becomes the wire's snake_case pin.
 *
 * Both URLs are sent and they are not interchangeable: `image_url` may be the backend's own
 * `/api/image` proxy and is display-only, while `origin_image_url` is the file the server
 * fetches and re-hosts on fal. Sending the proxy URL as the origin would put a localhost URL
 * in front of fal's fetcher, which is the exact failure this pair exists to prevent.
 */
function toPayload(pin: PinnedRef): PinnedRefPayload {
  return {
    id: pin.id,
    title: pin.title,
    lane: pin.lane,
    image_url: pin.imageUrl,
    origin_image_url: pin.originImageUrl,
    source_url: pin.sourceUrl,
  }
}

function correlationIdOf(body: unknown): string {
  if (typeof body === 'object' && body !== null && 'correlation_id' in body) {
    const value = (body as { correlation_id: unknown }).correlation_id
    if (typeof value === 'string') {
      return value
    }
  }
  return 'unknown'
}

/** What the user is told when the server answered but there is no image. */
const REFUSALS: Record<Exclude<GenerateResponse['status'], 'ok'>, string> = {
  timeout: 'Generation ran past 45 seconds and we stopped waiting.',
  already_generating: 'A generation is already running for this session.',
  // Overridden below whenever the server named the pins. This is the fallback for the case
  // where it could not.
  reference_unavailable: 'The pinned images could not be used for conditioning.',
}

/**
 * The refusal, in the user's terms.
 *
 * `reference_unavailable` is the only one they can act on, so it says what to do rather than
 * what went wrong — and it counts, because telling someone to unpin "them" when exactly one pin
 * is at fault is a worse instruction than telling them to unpin "it". Reached only when fal
 * rejects references the server had already fetched and re-hosted; a pin the server itself
 * could not fetch is dropped instead, and the generation still produces an image.
 */
function refusalFor(result: GenerateResponse): string {
  if (result.status === 'ok') {
    return ''
  }
  const dropped = result.unavailable_references?.length ?? 0
  if (result.status === 'reference_unavailable' && dropped > 0) {
    return dropped === 1
      ? 'One pinned image could not be used for conditioning — unpin it to generate without it.'
      : `${dropped} pinned images could not be used for conditioning — unpin them to generate without them.`
  }
  return REFUSALS[result.status]
}

async function requestGeneration(payload: GenerateRequest): Promise<GenerateResponse> {
  const response = await fetch(apiUrl('/v1/generate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  })
  const body: unknown = await response.json()
  if (!response.ok) {
    throw new GenerationError('Generation failed.', correlationIdOf(body))
  }
  // The backend is the shape authority: these types are generated from its OpenAPI schema by
  // `pnpm gen:api`, so a drift is a build error rather than a runtime surprise.
  return body as GenerateResponse
}

export class GenerationError extends Error {
  constructor(
    message: string,
    readonly correlationId: string,
  ) {
    super(message)
    this.name = 'GenerationError'
  }
}

export interface GenerateHandle {
  generate: () => void
  status: GenerationStatus
  /** False when there is nothing to generate from, or one is already in flight. */
  canGenerate: boolean
}

export function transcriptForGeneration(
  transcript: string,
  segments: readonly TranscriptSegment[],
): string {
  if (segments.length === 0) {
    return transcript.trim()
  }
  return segments
    .filter((segment) => voiceCommandFor(segment.text) === null)
    .map((segment) => segment.text.trim())
    .filter(Boolean)
    .join(' ')
}

/**
 * Turns the session into one image.
 *
 * The pins are sent whole, including the ones with no URL at all. That is the honest shape of
 * the degradation: the server folds every pin's title into the synthesis, fetches and re-hosts
 * the ones carrying an origin image, and reports `reference_count` and `unavailable_references`
 * so nothing here has to guess which happened.
 *
 * The in-flight guard is doubled deliberately. This one keeps the button honest; the server's
 * is the one that actually protects the account, because fal allows two concurrent requests and
 * a browser is not a thing to trust with that.
 */
export function useGenerate(): GenerateHandle {
  const sessionId = useSessionStore((state) => state.sessionId)
  const transcript = useSessionStore((state) => state.transcript)
  const transcriptSegments = useSessionStore((state) => state.transcriptSegments)
  const pinned = useSessionStore((state) => state.pinned)
  const status = useSessionStore((state) => state.generationStatus)
  const startGenerating = useSessionStore((state) => state.startGenerating)
  const settleGeneration = useSessionStore((state) => state.settleGeneration)
  const failGeneration = useSessionStore((state) => state.failGeneration)

  const promptTranscript = transcriptForGeneration(transcript, transcriptSegments)
  const ready = Boolean(sessionId) && promptTranscript.length > 0
  const canGenerate = ready && status !== 'generating'

  const generate = useCallback(() => {
    if (!sessionId || !promptTranscript || status === 'generating') {
      return
    }
    startGenerating()
    void requestGeneration({
      session_id: sessionId,
      transcript: promptTranscript,
      pins: pinned.map(toPayload),
    })
      .then((result) => {
        if (result.status !== 'ok') {
          failGeneration({
            message: refusalFor(result),
            correlationId: result.correlation_id,
          })
          return
        }
        if (!result.image_url) {
          failGeneration({
            message: 'The server reported a generation with no image.',
            correlationId: result.correlation_id,
          })
          return
        }
        settleGeneration({
          imageUrl: result.image_url,
          prompt: result.prompt,
          model: result.model,
          referenceCount: result.reference_count,
          // Optional on the wire because it defaults to empty server-side, and "the server did
          // not say" and "nothing was dropped" are the same claim here.
          unavailableReferences: result.unavailable_references ?? [],
        })
      })
      .catch((error: unknown) => {
        failGeneration({
          message: 'Generation failed.',
          correlationId: error instanceof GenerationError ? error.correlationId : 'unknown',
        })
      })
  }, [
    failGeneration,
    pinned,
    promptTranscript,
    sessionId,
    settleGeneration,
    startGenerating,
    status,
  ])

  return { generate, status, canGenerate }
}
