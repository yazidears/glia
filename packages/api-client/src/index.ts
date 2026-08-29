import type { components } from './schema'

export type RealtimeTokenRequest = components['schemas']['RealtimeTokenRequest']
export type RealtimeTokenResponse = components['schemas']['RealtimeTokenResponse']

export {
  parseRealtimeTokenResponse,
  parseServerMessage,
  type ClientMessage,
  type ConnectionState,
  type IntentUpdated,
  type ServerMessage,
  type TranscriptAccepted,
  type VisualIntent,
} from './realtime'
