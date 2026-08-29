import type { GenerateRequest, GenerateResponse, PinnedRefPayload } from '@glia/api-client'
import { useCallback } from 'react'
import { type GenerationStatus, type PinnedRef, useSessionStore } from '@/stores/session'

// The server caps its own poll at ~45s and answers with a typed timeout rather than hanging.
// This has to outlast that, or the browser abandons a generation the account has already paid
// for and shows a network error in place of the server's honest one.
const REQUEST_TIMEOUT_MS = 75_000

function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  return `${base}${path}`
}

/** The one place the store's camelCase pin becomes the wire's snake_case pin. */
function toPayload(pin: PinnedRef): PinnedRefPayload {
  return {
    id: pin.id,
    title: pin.title,
    lane: pin.lane,
    image_url: pin.imageUrl,
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
  // The only one the user can fix, so it says what to do rather than what went wrong. Measured
  // live: fal cannot fetch upload.wikimedia.org, which answers its blank User-Agent with a 403.
  reference_unavailable:
    'One pinned image could not be fetched for conditioning — unpin it to generate without it.',
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

/**
 * Turns the session into one image.
 *
 * The pins are sent whole, including the ones with no `imageUrl`. That is the honest shape of
 * the degradation: the server folds every pin's title into the synthesis and passes only the
 * fetchable ones to fal as references, then reports `reference_count` so nothing here has to
 * guess which happened.
 *
 * The in-flight guard is doubled deliberately. This one keeps the button honest; the server's
 * is the one that actually protects the account, because fal allows two concurrent requests and
 * a browser is not a thing to trust with that.
 */
export function useGenerate(): GenerateHandle {
  const sessionId = useSessionStore((state) => state.sessionId)
  const transcript = useSessionStore((state) => state.transcript)
  const pinned = useSessionStore((state) => state.pinned)
  const status = useSessionStore((state) => state.generationStatus)
  const startGenerating = useSessionStore((state) => state.startGenerating)
  const settleGeneration = useSessionStore((state) => state.settleGeneration)
  const failGeneration = useSessionStore((state) => state.failGeneration)

  const ready = Boolean(sessionId) && transcript.trim().length > 0
  const canGenerate = ready && status !== 'generating'

  const generate = useCallback(() => {
    if (!sessionId || !transcript.trim() || status === 'generating') {
      return
    }
    startGenerating()
    void requestGeneration({
      session_id: sessionId,
      transcript,
      pins: pinned.map(toPayload),
    })
      .then((result) => {
        if (result.status !== 'ok') {
          failGeneration({
            message: REFUSALS[result.status],
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
        })
      })
      .catch((error: unknown) => {
        failGeneration({
          message: 'Generation failed.',
          correlationId: error instanceof GenerationError ? error.correlationId : 'unknown',
        })
      })
  }, [failGeneration, pinned, sessionId, settleGeneration, startGenerating, status, transcript])

  return { generate, status, canGenerate }
}
