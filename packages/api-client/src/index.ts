import type { components } from './schema'

export type HealthResponse = components['schemas']['HealthResponse']
export type RealtimeTokenRequest = components['schemas']['RealtimeTokenRequest']
export type RealtimeTokenResponse = components['schemas']['RealtimeTokenResponse']

export type DiscoverRequest = components['schemas']['DiscoverRequest']
export type DiscoverResponse = components['schemas']['DiscoverResponse']
export type DiscoveryStatus = DiscoverResponse['status']
export type ResolvedEntity = components['schemas']['CalaEntityHit']
export type EvidenceItem = components['schemas']['EvidenceItem']
export type EvidenceOrigin = components['schemas']['CalaOrigin']
export type LedgerSnapshot = components['schemas']['LedgerSnapshot']
export type LaneHealth = components['schemas']['LaneHealth']

export type GenerateRequest = components['schemas']['GenerateRequest']
export type GenerateResponse = components['schemas']['GenerateResponse']
export type GenerateStatus = GenerateResponse['status']
/**
 * The wire shape of a pin. The store keeps its own camelCase `PinnedRef` — this is what that
 * becomes at the boundary, and the two are joined by one mapper so a rename on either side is
 * a type error rather than a silently dropped field.
 */
export type PinnedRefPayload = components['schemas']['PinnedRef']

/**
 * The languages the transcription session may be told to expect. Derived from the generated
 * schema rather than restated, so the day someone edits `ExpectedLanguage` in `contracts.py`
 * the frontend stops compiling instead of quietly sending a value the server will reject.
 */
export type ExpectedLanguage = NonNullable<RealtimeTokenRequest['languages']>[number]

/**
 * The same four values as a runtime list, for anything that has to render or validate them.
 * The annotation is the guard: a language removed from the contract fails to assign here.
 */
export const EXPECTED_LANGUAGES: readonly ExpectedLanguage[] = ['ca', 'en', 'es', 'fr']

/** The server's own first choice in `default_languages()`. */
export const DEFAULT_EXPECTED_LANGUAGE: ExpectedLanguage = 'en'

export function isExpectedLanguage(value: unknown): value is ExpectedLanguage {
  return EXPECTED_LANGUAGES.includes(value as ExpectedLanguage)
}

export function parseHealthResponse(value: unknown): HealthResponse | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null
  }
  const candidate = value as Record<string, unknown>
  if (
    typeof candidate.status !== 'string' ||
    typeof candidate.service !== 'string' ||
    typeof candidate.mode !== 'string' ||
    typeof candidate.realtime !== 'string' ||
    typeof candidate.distiller !== 'string' ||
    typeof candidate.image_discovery !== 'boolean'
  ) {
    return null
  }
  return {
    status: candidate.status,
    service: candidate.service,
    mode: candidate.mode,
    realtime: candidate.realtime,
    distiller: candidate.distiller,
    image_discovery: candidate.image_discovery,
    // Optional on the wire, so an older server that predates the lane probe parses fine
    // rather than failing the whole health check over a field it never sent.
    lanes: Array.isArray(candidate.lanes) ? (candidate.lanes as LaneHealth[]) : [],
  }
}

export {
  type Candidate,
  type CandidateLane,
  type CandidatesBatch,
  type ClientMessage,
  type ConnectionState,
  type IntentUpdated,
  type LedgerUpdated,
  parseRealtimeTokenResponse,
  parseServerMessage,
  type ServerMessage,
  type TranscriptAccepted,
  type VisualIntent,
} from './realtime'
