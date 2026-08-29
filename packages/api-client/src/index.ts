import type { components } from './schema'

export type RealtimeTokenRequest = components['schemas']['RealtimeTokenRequest']
export type RealtimeTokenResponse = components['schemas']['RealtimeTokenResponse']

export type DiscoverRequest = components['schemas']['DiscoverRequest']
export type DiscoverResponse = components['schemas']['DiscoverResponse']
export type DiscoveryStatus = DiscoverResponse['status']
export type ResolvedEntity = components['schemas']['CalaEntityHit']
export type EvidenceItem = components['schemas']['EvidenceItem']
export type EvidenceOrigin = components['schemas']['CalaOrigin']
export type LedgerSnapshot = components['schemas']['LedgerSnapshot']

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
