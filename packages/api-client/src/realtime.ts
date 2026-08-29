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
