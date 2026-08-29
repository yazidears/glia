import { type HealthResponse, parseHealthResponse } from '@glia/api-client'
import { useQuery } from '@tanstack/react-query'

const REQUEST_TIMEOUT_MS = 4_000

export interface Capabilities {
  /** The server can return image candidates. False while the discovery pipeline is absent. */
  imageDiscovery: boolean
}

/** What a browser that cannot reach the API is allowed to believe it can do. */
const NO_CAPABILITIES: Capabilities = { imageDiscovery: false }

function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  return `${base}${path}`
}

async function fetchHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(apiUrl('/health'), {
    signal: AbortSignal.any([signal, AbortSignal.timeout(REQUEST_TIMEOUT_MS)]),
  })
  if (!response.ok) {
    throw new Error('The server did not report its capabilities.')
  }
  const health = parseHealthResponse(await response.json())
  if (!health) {
    throw new Error('The server reported an unrecognised health shape.')
  }
  return health
}

/**
 * Asks the API once what it can actually do.
 *
 * `/health` already carries the shape of the deployment, so the capability rides on it rather
 * than on an endpoint invented for one boolean. Only the settings form calls this, and that form
 * exists only while the dialog is open, so the empty opening screen makes no request at all. It
 * never refetches: a capability that changes mid-session is a redeploy, not a state change.
 *
 * Failure is not "assume yes". An unreachable server proves nothing, and offering an option the
 * product may not honour is the exact dishonesty this gate exists to prevent.
 */
export function useCapabilities(): Capabilities {
  const { data } = useQuery({
    queryKey: ['capabilities'],
    queryFn: ({ signal }) => fetchHealth(signal),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  return data ? { imageDiscovery: data.image_discovery } : NO_CAPABILITIES
}
