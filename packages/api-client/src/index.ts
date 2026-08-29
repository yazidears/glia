import type { components } from './schema'

export type HealthResponse = components['schemas']['HealthResponse']
export type RealtimeTokenRequest = components['schemas']['RealtimeTokenRequest']
export type RealtimeTokenResponse = components['schemas']['RealtimeTokenResponse']

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
  }
}

export {
  type ClientMessage,
  type ConnectionState,
  type IntentUpdated,
  parseRealtimeTokenResponse,
  parseServerMessage,
  type ServerMessage,
  type TranscriptAccepted,
  type VisualIntent,
} from './realtime'
