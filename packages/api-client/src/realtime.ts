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
export type IdeaSource = 'local' | 'openai'
export type IntentChangeReason = 'initial' | 'subject' | 'medium' | 'era' | 'visual_attributes'
export type CandidateLane = 'cited' | 'open'

export interface Candidate {
  id: string
  lane: CandidateLane
  image_url: string
  origin_image_url: string | null
  source_url: string
  publisher: string | null
  title: string | null
  evidence: string | null
  licence: string | null
  entity_name: string | null
  entity_type: string | null
  width: number | null
  height: number | null
  score: number
}

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

export interface CandidatesBatch {
  type: 'candidates.batch'
  revision: number
  candidates: Candidate[]
}

export interface IdeasUpdated {
  type: 'ideas.updated'
  revision: number
  ideas: string[]
  keywords: string[]
  source: IdeaSource
}

export interface LedgerUpdated {
  type: 'ledger.updated'
  cala_queries: number
  references: number
  cited: number
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
  | IdeasUpdated
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

const intentSources = new Set<IntentSource>(['fixture', 'local', 'pioneer'])
const ideaSources = new Set<IdeaSource>(['local', 'openai'])
const intentChangeReasons = new Set<IntentChangeReason>([
  'initial',
  'subject',
  'medium',
  'era',
  'visual_attributes',
])
const candidateLanes = new Set<CandidateLane>(['cited', 'open'])

function parseCandidates(value: unknown): Candidate[] | null {
  if (!Array.isArray(value)) {
    return null
  }
  const candidates: Candidate[] = []
  for (const candidate of value) {
    if (
      !isRecord(candidate) ||
      !hasString(candidate, 'id') ||
      !hasString(candidate, 'lane') ||
      !hasString(candidate, 'image_url') ||
      !hasString(candidate, 'source_url') ||
      !candidateLanes.has(candidate.lane as CandidateLane) ||
      typeof candidate.score !== 'number'
    ) {
      return null
    }
    candidates.push({
      id: candidate.id as string,
      lane: candidate.lane as CandidateLane,
      image_url: candidate.image_url as string,
      origin_image_url:
        typeof candidate.origin_image_url === 'string' ? candidate.origin_image_url : null,
      source_url: candidate.source_url as string,
      publisher: typeof candidate.publisher === 'string' ? candidate.publisher : null,
      title: typeof candidate.title === 'string' ? candidate.title : null,
      evidence: typeof candidate.evidence === 'string' ? candidate.evidence : null,
      licence: typeof candidate.licence === 'string' ? candidate.licence : null,
      entity_name: typeof candidate.entity_name === 'string' ? candidate.entity_name : null,
      entity_type: typeof candidate.entity_type === 'string' ? candidate.entity_type : null,
      width: typeof candidate.width === 'number' ? candidate.width : null,
      height: typeof candidate.height === 'number' ? candidate.height : null,
      score: candidate.score as number,
    })
  }
  return candidates
}

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
      const candidates = parseCandidates(value.candidates)
      if (candidates && hasNumber(value, 'revision')) {
        return {
          type: 'candidates.batch',
          revision: value.revision as number,
          candidates,
        }
      }
      return null
    }
    case 'ideas.updated':
      if (
        hasNumber(value, 'revision') &&
        hasStringArray(value, 'ideas') &&
        hasStringArray(value, 'keywords') &&
        hasString(value, 'source') &&
        ideaSources.has(value.source as IdeaSource)
      ) {
        return value as unknown as IdeasUpdated
      }
      return null
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
