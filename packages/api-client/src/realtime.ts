export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'error'

export interface VisualIntent {
  subject: string
  moods: string[]
  styles: string[]
  palette: string[]
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
}

export type ServerMessage =
  | { type: 'session.ready'; session_id: string; debounce_ms: number; heartbeat_interval_ms: number }
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
  const moods = value.moods
  const styles = value.styles
  const palette = value.palette
  if (
    !Array.isArray(moods) ||
    !moods.every((item) => typeof item === 'string') ||
    !Array.isArray(styles) ||
    !styles.every((item) => typeof item === 'string') ||
    !Array.isArray(palette) ||
    !palette.every((item) => typeof item === 'string')
  ) {
    return null
  }
  return { subject: value.subject as string, moods, styles, palette }
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
      if (hasString(value, 'item_id') && hasString(value, 'transcript') && hasBoolean(value, 'complete')) {
        return value as unknown as TranscriptAccepted
      }
      return null
    case 'intent.updated': {
      const intent = parseVisualIntent(value.intent)
      if (
        intent &&
        hasNumber(value, 'revision') &&
        hasString(value, 'transcript') &&
        hasBoolean(value, 'stable')
      ) {
        return {
          type: 'intent.updated',
          revision: value.revision as number,
          transcript: value.transcript as string,
          intent,
          stable: value.stable as boolean,
        }
      }
      return null
    }
    case 'pong':
      return hasString(value, 'event_id') ? (value as unknown as ServerMessage) : null
    case 'error':
      if (hasString(value, 'code') && hasString(value, 'detail') && hasBoolean(value, 'recoverable')) {
        return value as unknown as ServerMessage
      }
      return null
    default:
      return null
  }
}
