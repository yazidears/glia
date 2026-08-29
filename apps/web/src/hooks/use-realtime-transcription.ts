import {
  type ClientMessage,
  parseRealtimeTokenResponse,
  parseServerMessage,
  type RealtimeTokenRequest,
  type RealtimeTokenResponse,
} from '@glia/api-client'
import { useEffect } from 'react'
import { useSessionStore } from '@/stores/session'

const REQUEST_TIMEOUT_MS = 8_000
const CLIENT_ID_KEY = 'glia:client-id:v1'
const FIXTURE_TRANSCRIPT =
  'A lonely cobalt observatory above the Mediterranean, cinematic, cold, and softly lit.'

type UnknownRecord = Record<string, unknown>

interface TranscriptItem {
  order: number
  text: string
  complete: boolean
}

class RealtimeProviderError extends Error {
  constructor(
    message: string,
    readonly code: string | null,
  ) {
    super(message)
    this.name = 'RealtimeProviderError'
  }
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function clientId(): string {
  try {
    const current = window.localStorage.getItem(CLIENT_ID_KEY)
    if (current) {
      return current
    }
    const created = crypto.randomUUID()
    window.localStorage.setItem(CLIENT_ID_KEY, created)
    return created
  } catch {
    return crypto.randomUUID()
  }
}

function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  return `${base}${path}`
}

function websocketUrl(): string {
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL
  }
  const url = new URL('/ws', window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

function requestSignal(parent: AbortSignal): AbortSignal {
  return AbortSignal.any([parent, AbortSignal.timeout(REQUEST_TIMEOUT_MS)])
}

async function fetchToken(signal: AbortSignal) {
  const payload: RealtimeTokenRequest = {
    client_id: clientId(),
    languages: ['en', 'es', 'ca'],
  }
  const response = await fetch(apiUrl('/api/realtime-token'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: requestSignal(signal),
  })
  const body: unknown = await response.json()
  if (!response.ok) {
    const detail =
      isRecord(body) && typeof body.detail === 'string'
        ? body.detail
        : 'Unable to start transcription.'
    const code = isRecord(body) && typeof body.code === 'string' ? body.code : null
    throw new RealtimeProviderError(detail, code)
  }
  const token = parseRealtimeTokenResponse(body)
  if (!token) {
    throw new Error('The server returned an invalid transcription credential.')
  }
  return token
}

function delay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timeout = window.setTimeout(resolve, milliseconds)
    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timeout)
        resolve()
      },
      { once: true },
    )
  })
}

async function playFixture(socket: WebSocket, signal: AbortSignal): Promise<void> {
  const itemId = `fixture-${crypto.randomUUID()}`
  const chunks = FIXTURE_TRANSCRIPT.match(/\S+\s*/g) ?? [FIXTURE_TRANSCRIPT]
  for (const chunk of chunks) {
    if (signal.aborted) {
      return
    }
    send(socket, {
      type: 'transcript.delta',
      event_id: crypto.randomUUID(),
      item_id: itemId,
      delta: chunk,
    })
    await delay(110, signal)
  }
  if (!signal.aborted) {
    send(socket, {
      type: 'transcript.completed',
      event_id: crypto.randomUUID(),
      item_id: itemId,
      transcript: FIXTURE_TRANSCRIPT,
    })
  }
}

function openBackendSocket(
  signal: AbortSignal,
  onMessage: (event: MessageEvent<string>) => void,
): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(websocketUrl())
    const fail = () => reject(new Error('Unable to connect to Glia.'))
    socket.addEventListener('message', onMessage)
    socket.addEventListener('open', () => resolve(socket), { once: true })
    socket.addEventListener('error', fail, { once: true })
    signal.addEventListener(
      'abort',
      () => {
        socket.close()
        reject(new DOMException('Connection cancelled', 'AbortError'))
      },
      { once: true },
    )
  })
}

function send(socket: WebSocket, message: ClientMessage): void {
  if (socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(message))
  }
}

function parseOpenAIEvent(raw: string): UnknownRecord | null {
  try {
    const value: unknown = JSON.parse(raw)
    return isRecord(value) ? value : null
  } catch {
    return null
  }
}

export function useRealtimeTranscription(): void {
  const stream = useSessionStore((state) => state.stream)
  const setConnection = useSessionStore((state) => state.setConnection)
  const setTranscriptState = useSessionStore((state) => state.setTranscriptState)
  const setIntent = useSessionStore((state) => state.setIntent)
  const resetRealtime = useSessionStore((state) => state.resetRealtime)

  useEffect(() => {
    if (!stream) {
      setConnection('idle')
      return
    }

    resetRealtime()

    const controller = new AbortController()
    const peer = new RTCPeerConnection()
    const events = peer.createDataChannel('oai-events')
    let backend: WebSocket | null = null
    let providerTranscriptionSeen = false
    let nextItemOrder = 0
    const transcriptItems = new Map<string, TranscriptItem>()
    const seenProviderEvents = new Set<string>()

    const updateTranscriptItem = (
      itemId: string,
      value: string,
      complete: boolean,
      update: (current: string, incoming: string) => string,
    ): void => {
      const current = transcriptItems.get(itemId)
      if (current?.complete && !complete) {
        return
      }
      transcriptItems.set(itemId, {
        order: current?.order ?? nextItemOrder++,
        text: update(current?.text ?? '', value),
        complete,
      })
      const orderedItems = [...transcriptItems.entries()].sort(
        (left, right) => left[1].order - right[1].order,
      )
      const transcript = orderedItems
        .map(([, item]) => item.text.trim())
        .filter((text) => text.length > 0)
        .join(' ')
      setTranscriptState(
        transcript,
        orderedItems
          .map(([segmentItemId, item]) => ({
            itemId: segmentItemId,
            text: item.text.trim(),
            complete: item.complete,
          }))
          .filter((item) => item.text.length > 0),
      )
    }

    setConnection('connecting')

    const onBackendMessage = (event: MessageEvent<string>): void => {
      if (controller.signal.aborted) {
        return
      }
      const message = parseServerMessage(event.data)
      if (!message) {
        return
      }
      if (message.type === 'transcript.accepted') {
        // Provider events paint locally with zero round-trip latency. Backend echoes can arrive
        // one delta behind, so they are only the source of truth for the deterministic fixture.
        if (providerTranscriptionSeen) {
          return
        }
        updateTranscriptItem(
          message.item_id,
          message.transcript,
          message.complete,
          (_current, transcript) => transcript,
        )
      } else if (message.type === 'intent.updated') {
        setIntent(message.intent)
      } else if (message.type === 'error' && !message.recoverable) {
        setConnection('error', message.detail)
      }
    }

    events.addEventListener('message', (event: MessageEvent<string>) => {
      if (controller.signal.aborted) {
        return
      }
      const message = parseOpenAIEvent(event.data)
      if (!message || typeof message.type !== 'string' || typeof message.item_id !== 'string') {
        return
      }
      const providerEventId =
        typeof message.event_id === 'string' ? message.event_id : crypto.randomUUID()
      if (seenProviderEvents.has(providerEventId)) {
        return
      }
      seenProviderEvents.add(providerEventId)
      if (
        message.type === 'conversation.item.input_audio_transcription.delta' &&
        typeof message.delta === 'string'
      ) {
        providerTranscriptionSeen = true
        updateTranscriptItem(
          message.item_id,
          message.delta,
          false,
          (current, delta) => current + delta,
        )
        if (backend) {
          send(backend, {
            type: 'transcript.delta',
            event_id: providerEventId,
            item_id: message.item_id,
            delta: message.delta,
          })
        }
      } else if (
        message.type === 'conversation.item.input_audio_transcription.completed' &&
        typeof message.transcript === 'string'
      ) {
        providerTranscriptionSeen = true
        updateTranscriptItem(
          message.item_id,
          message.transcript,
          true,
          (_current, transcript) => transcript,
        )
        if (backend) {
          send(backend, {
            type: 'transcript.completed',
            event_id: providerEventId,
            item_id: message.item_id,
            transcript: message.transcript,
          })
        }
      }
    })
    events.addEventListener('open', () => setConnection('connected'))
    events.addEventListener('error', () =>
      setConnection('error', 'The live transcription channel failed.'),
    )
    peer.addEventListener('connectionstatechange', () => {
      if (peer.connectionState === 'failed') {
        setConnection('error', 'The live audio connection failed.')
      }
    })

    for (const track of stream.getAudioTracks()) {
      peer.addTrack(track, stream)
    }

    async function connect(): Promise<void> {
      try {
        backend = await openBackendSocket(controller.signal, onBackendMessage)
        let token: RealtimeTokenResponse
        try {
          token = await fetchToken(controller.signal)
        } catch (error) {
          if (error instanceof RealtimeProviderError && error.code === 'realtime_not_configured') {
            setConnection('connected')
            await playFixture(backend, controller.signal)
            return
          }
          throw error
        }
        const offer = await peer.createOffer()
        await peer.setLocalDescription(offer)
        if (!offer.sdp) {
          throw new Error('The browser could not create an audio offer.')
        }
        const answer = await fetch('https://api.openai.com/v1/realtime/calls', {
          method: 'POST',
          body: offer.sdp,
          headers: {
            Authorization: `Bearer ${token.value}`,
            'Content-Type': 'application/sdp',
          },
          signal: requestSignal(controller.signal),
        })
        if (!answer.ok) {
          throw new Error('OpenAI rejected the live audio connection.')
        }
        await peer.setRemoteDescription({ type: 'answer', sdp: await answer.text() })
      } catch (error) {
        if (!controller.signal.aborted) {
          setConnection(
            'error',
            error instanceof Error ? error.message : 'Unable to start transcription.',
          )
        }
      }
    }

    void connect()

    return () => {
      controller.abort()
      events.close()
      peer.close()
      backend?.close()
    }
  }, [resetRealtime, setConnection, setIntent, setTranscriptState, stream])
}
