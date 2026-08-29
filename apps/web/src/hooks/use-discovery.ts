import type { DiscoverRequest, DiscoverResponse } from '@glia/api-client'
import { type UseQueryResult, useQuery } from '@tanstack/react-query'
import { useSessionStore } from '@/stores/session'

// Generous, and measured rather than picked: a cold `knowledge/search` against the live Cala
// API took 45.7s on 29 Aug 2026. This has to outlast the server's own read timeout, or the
// browser abandons a query we have already paid for and the user sees an error instead.
const REQUEST_TIMEOUT_MS = 120_000

function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  return `${base}${path}`
}

/**
 * A problem document carries a correlation id and nothing else worth showing. The upstream
 * detail stays on the server, so this is all the UI has to say — and all it should.
 */
export class DiscoveryError extends Error {
  constructor(readonly correlationId: string) {
    super('Discovery failed.')
    this.name = 'DiscoveryError'
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

async function discover(payload: DiscoverRequest): Promise<DiscoverResponse> {
  const response = await fetch(apiUrl('/v1/discover'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  })
  const body: unknown = await response.json()
  if (!response.ok) {
    throw new DiscoveryError(correlationIdOf(body))
  }
  // The backend is the only shape authority here: these types are generated from its OpenAPI
  // schema by `pnpm gen:api`, so a drift is a build error rather than a runtime surprise.
  return body as DiscoverResponse
}

/**
 * Asks the backend what the speaker is talking about, once per settled turn.
 *
 * The query key is the settled transcript, which the store only advances when the backend
 * marks a turn `stable`. That is the client half of the guard: an interim delta never changes
 * the key, and a settled turn that repeats the same words never changes it either, so neither
 * can start a request. The server debounces and caches independently — the browser is not the
 * thing holding the credit budget, and this guard exists to keep the network quiet, not to be
 * trusted with the money.
 */
export function useDiscovery(): UseQueryResult<DiscoverResponse, Error> {
  const sessionId = useSessionStore((state) => state.sessionId)
  const settledTranscript = useSessionStore((state) => state.settledTranscript)
  const enabled = Boolean(sessionId) && settledTranscript.trim().length > 0

  return useQuery({
    queryKey: ['discovery', sessionId, settledTranscript],
    enabled,
    // Nothing about a settled turn changes after the fact, so nothing should ever refetch it.
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
    queryFn: () => discover({ transcript: settledTranscript, session_id: sessionId ?? '' }),
  })
}
