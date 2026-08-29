export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'error'

export interface VisualIntent {
  subject: string
  moods: string[]
  styles: string[]
  palette: string[]
  composition: string
  medium: string
  era: string
}

export type IntentSource = 'fixture' | 'local' | 'pioneer'

/**
 * Mirrors of `Candidate`, `CandidatesBatch` and `LedgerUpdated` in
 * `apps/api/glia/contracts.py`.
 *
 * Hand-written on purpose: these travel over the WebSocket, which is not in the OpenAPI
 * document, so `pnpm gen:api` cannot produce them and will not notice if they drift.
 * Keep the field lists in step with `contracts.py` — the parsers below are the only
 * thing standing between a changed server shape and a broken grid.
 */
export type CandidateLane = 'cited' | 'open'

export interface Candidate {
  id: string
  lane: CandidateLane
  /** Already routed through the API's `/api/image` proxy. Render it verbatim. */
  image_url: string
  source_url: string
  publisher: string | null
  title: string | null
  evidence: string | null
  licence: string | null
  entity_name: string | null
  entity_type: string | null
  /** Intrinsic dimensions, so a tile can reserve its aspect box before the image loads. */
  width: number | null
  height: number | null
  score: number
}

export interface CandidatesBatch {
  type: 'candidates.batch'
  revision: number
  candidates: Candidate[]
}

export interface LedgerUpdated {
  type: 'ledger.updated'
  cala_queries: number
  references: number
  cited: number
}

export type IntentChangeReason = 'initial' | 'subject' | 'medium' | 'era' | 'visual_attributes'

export interface TranscriptAccepted {
  type: 'transcript.accepted'
  item_id: string
  transcript: string
  complete: boolean
}

export interface IntentUpdated {
  type: 'intent.updated'
  revision: number
  transcript: string
  intent: VisualIntent
  stable: boolean
  source: IntentSource
  should_discover: boolean
  change_reasons: IntentChangeReason[]
}

export type ServerMessage =
  | {
      type: 'session.ready'
      session_id: string
      debounce_ms: number
      heartbeat_interval_ms: number
    }
  | TranscriptAccepted
  | IntentUpdated
  | CandidatesBatch
  | LedgerUpdated
  | { type: 'pong'; event_id: string }
  | { type: 'error'; code: string; detail: string; recoverable: boolean }

export type ClientMessage =
  | { type: 'transcript.delta'; event_id: string; item_id: string; delta: string }
  | { type: 'transcript.completed'; event_id: string; item_id: string; transcript: string }
  | { type: 'ping'; event_id: string }

type UnknownRecord = Record<string, unknown>

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasString(value: UnknownRecord, key: string): boolean {
  return typeof value[key] === 'string'
}

function hasNumber(value: UnknownRecord, key: string): boolean {
  return typeof value[key] === 'number'
}

function hasBoolean(value: UnknownRecord, key: string): boolean {
  return typeof value[key] === 'boolean'
}

function hasStringArray(value: UnknownRecord, key: string): boolean {
  const candidate = value[key]
  return Array.isArray(candidate) && candidate.every((item) => typeof item === 'string')
}

function parseJson(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown
  } catch {
    return null
  }
}

export function parseRealtimeTokenResponse(value: unknown): {
  value: string
  expires_at: number
  model: string
} | null {
  if (
    !isRecord(value) ||
    !hasString(value, 'value') ||
    !hasNumber(value, 'expires_at') ||
    !hasString(value, 'model')
  ) {
    return null
  }
  return {
    value: value.value as string,
    expires_at: value.expires_at as number,
    model: value.model as string,
  }
}

function parseVisualIntent(value: unknown): VisualIntent | null {
  if (!isRecord(value) || !hasString(value, 'subject')) {
    return null
  }
  if (
    !hasStringArray(value, 'moods') ||
    !hasStringArray(value, 'styles') ||
    !hasStringArray(value, 'palette') ||
    !hasString(value, 'composition') ||
    !hasString(value, 'medium') ||
    !hasString(value, 'era')
  ) {
    return null
  }
  return {
    subject: value.subject as string,
    moods: value.moods as string[],
    styles: value.styles as string[],
    palette: value.palette as string[],
    composition: value.composition as string,
    medium: value.medium as string,
    era: value.era as string,
  }
}

function nullableString(value: UnknownRecord, key: string): boolean {
  return value[key] === null || typeof value[key] === 'string'
}

function nullableNumber(value: UnknownRecord, key: string): boolean {
  return value[key] === null || typeof value[key] === 'number'
}

const candidateLanes = new Set<CandidateLane>(['cited', 'open'])

/**
 * One candidate, or null. A tile is only as safe as this: everything it renders as text
 * is proven to be a string here, and `width`/`height` are proven to be numbers or null
 * so the reserved aspect box is never computed from something that is neither.
 */
function parseCandidate(value: unknown): Candidate | null {
  if (!isRecord(value)) {
    return null
  }
  if (
    !hasString(value, 'id') ||
    !hasString(value, 'lane') ||
    !candidateLanes.has(value.lane as CandidateLane) ||
    !hasString(value, 'image_url') ||
    !hasString(value, 'source_url') ||
    !hasNumber(value, 'score')
  ) {
    return null
  }
  const nullableStrings = [
    'publisher',
    'title',
    'evidence',
    'licence',
    'entity_name',
    'entity_type',
  ]
  if (!nullableStrings.every((key) => nullableString(value, key))) {
    return null
  }
  if (!nullableNumber(value, 'width') || !nullableNumber(value, 'height')) {
    return null
  }
  return {
    id: value.id as string,
    lane: value.lane as CandidateLane,
    image_url: value.image_url as string,
    source_url: value.source_url as string,
    publisher: value.publisher as string | null,
    title: value.title as string | null,
    evidence: value.evidence as string | null,
    licence: value.licence as string | null,
    entity_name: value.entity_name as string | null,
    entity_type: value.entity_type as string | null,
    width: value.width as number | null,
    height: value.height as number | null,
    score: value.score as number,
  }
}

const intentSources = new Set<IntentSource>(['fixture', 'local', 'pioneer'])
const intentChangeReasons = new Set<IntentChangeReason>([
  'initial',
  'subject',
  'medium',
  'era',
  'visual_attributes',
])

export function parseServerMessage(raw: string): ServerMessage | null {
  const value = parseJson(raw)
  if (!isRecord(value) || !hasString(value, 'type')) {
    return null
  }
  switch (value.type) {
    case 'session.ready':
      if (
        hasString(value, 'session_id') &&
        hasNumber(value, 'debounce_ms') &&
        hasNumber(value, 'heartbeat_interval_ms')
      ) {
        return value as unknown as ServerMessage
      }
      return null
    case 'transcript.accepted':
      if (
        hasString(value, 'item_id') &&
        hasString(value, 'transcript') &&
        hasBoolean(value, 'complete')
      ) {
        return value as unknown as TranscriptAccepted
      }
      return null
    case 'intent.updated': {
      const intent = parseVisualIntent(value.intent)
      if (
        intent &&
        hasNumber(value, 'revision') &&
        hasString(value, 'transcript') &&
        hasBoolean(value, 'stable') &&
        hasString(value, 'source') &&
        intentSources.has(value.source as IntentSource) &&
        hasBoolean(value, 'should_discover') &&
        hasStringArray(value, 'change_reasons') &&
        (value.change_reasons as string[]).every((reason) =>
          intentChangeReasons.has(reason as IntentChangeReason),
        )
      ) {
        return {
          type: 'intent.updated',
          revision: value.revision as number,
          transcript: value.transcript as string,
          intent,
          stable: value.stable as boolean,
          source: value.source as IntentSource,
          should_discover: value.should_discover as boolean,
          change_reasons: value.change_reasons as IntentChangeReason[],
        }
      }
      return null
    }
    case 'candidates.batch': {
      if (!hasNumber(value, 'revision') || !Array.isArray(value.candidates)) {
        return null
      }
      // One malformed candidate drops itself, not the wave. A batch is a best-effort
      // delivery of whatever the lanes found, and a grid short one tile beats a grid
      // short a whole wave.
      const candidates = value.candidates
        .map(parseCandidate)
        .filter((item): item is Candidate => item !== null)
      return { type: 'candidates.batch', revision: value.revision as number, candidates }
    }
    case 'ledger.updated':
      if (
        hasNumber(value, 'cala_queries') &&
        hasNumber(value, 'references') &&
        hasNumber(value, 'cited')
      ) {
        return value as unknown as LedgerUpdated
      }
      return null
    case 'pong':
      return hasString(value, 'event_id') ? (value as unknown as ServerMessage) : null
    case 'error':
      if (
        hasString(value, 'code') &&
        hasString(value, 'detail') &&
        hasBoolean(value, 'recoverable')
      ) {
        return value as unknown as ServerMessage
      }
      return null
    default:
      return null
  }
}
