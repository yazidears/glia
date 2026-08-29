import {
  type ClientMessage,
  type ExpectedLanguage,
  parseRealtimeTokenResponse,
  parseServerMessage,
  type RealtimeTokenRequest,
  type RealtimeTokenResponse,
} from '@glia/api-client'
import { useEffect } from 'react'
import { type AudioLevelHandle, primeAudioContext } from '@/hooks/use-audio-level'
import { useSessionStore } from '@/stores/session'
import { useSettings } from '@/stores/settings'

const REQUEST_TIMEOUT_MS = 8_000
const CLIENT_ID_KEY = 'glia:client-id:v1'
const VOICE_ENTER_RMS = 0.015
const VOICE_EXIT_RMS = 0.008
const COMMIT_SILENCE_MS = 650
const PCM_SAMPLE_RATE = 24_000
const MAX_DATA_CHANNEL_BUFFER_BYTES = 512_000
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

async function fetchToken(signal: AbortSignal, language: ExpectedLanguage) {
  const payload: RealtimeTokenRequest = {
    client_id: clientId(),
    languages: [language],
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

/**
 * The offline demo. It emits the same client messages a real provider would, so whoever consumes
 * them decides where they go — the backend when live discovery is on, the local transcript when
 * it is off and no message may leave the browser.
 */
async function playFixture(
  signal: AbortSignal,
  emit: (message: ClientMessage) => void,
): Promise<void> {
  const itemId = `fixture-${crypto.randomUUID()}`
  const chunks = FIXTURE_TRANSCRIPT.match(/\S+\s*/g) ?? [FIXTURE_TRANSCRIPT]
  for (const chunk of chunks) {
    if (signal.aborted) {
      return
    }
    emit({
      type: 'transcript.delta',
      event_id: crypto.randomUUID(),
      item_id: itemId,
      delta: chunk,
    })
    await delay(110, signal)
  }
  if (!signal.aborted) {
    emit({
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

function encodePcm24k(input: Float32Array, inputSampleRate: number): string {
  const ratio = inputSampleRate / PCM_SAMPLE_RATE
  const outputLength = Math.max(1, Math.floor(input.length / ratio))
  const bytes = new Uint8Array(outputLength * 2)
  const view = new DataView(bytes.buffer)

  for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
    const start = Math.floor(outputIndex * ratio)
    const end = Math.max(start + 1, Math.min(input.length, Math.floor((outputIndex + 1) * ratio)))
    let sum = 0
    for (let inputIndex = start; inputIndex < end; inputIndex += 1) {
      sum += input[inputIndex] ?? 0
    }
    const sample = Math.max(-1, Math.min(1, sum / (end - start)))
    view.setInt16(outputIndex * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }

  let binary = ''
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index] ?? 0)
  }
  return window.btoa(binary)
}

function startPcmStream(
  stream: MediaStream,
  channel: RTCDataChannel,
  signal: AbortSignal,
): () => void {
  const context = primeAudioContext()
  if (!context) {
    return () => undefined
  }

  const source = context.createMediaStreamSource(stream)
  // ScriptProcessor is deliberately used for this one-day Safari demo fallback: it is available
  // synchronously in the existing audio context, while AudioWorklet would require another public
  // module and an asynchronous load after the microphone gesture.
  const processor = context.createScriptProcessor(4096, 1, 1)
  const silentSink = context.createGain()
  silentSink.gain.value = 0

  processor.addEventListener('audioprocess', (event) => {
    event.outputBuffer.getChannelData(0).fill(0)
    if (
      signal.aborted ||
      channel.readyState !== 'open' ||
      channel.bufferedAmount >= MAX_DATA_CHANNEL_BUFFER_BYTES
    ) {
      return
    }
    channel.send(
      JSON.stringify({
        type: 'input_audio_buffer.append',
        audio: encodePcm24k(event.inputBuffer.getChannelData(0), context.sampleRate),
      }),
    )
  })

  source.connect(processor)
  processor.connect(silentSink)
  silentSink.connect(context.destination)

  return () => {
    processor.disconnect()
    source.disconnect()
    silentSink.disconnect()
  }
}

function startManualCommitLoop(
  audio: AudioLevelHandle,
  commit: () => void,
  signal: AbortSignal,
): () => void {
  let analyser: AnalyserNode | null = null
  let samples = new Float32Array(0)
  let frame: number | null = null
  let speaking = false
  let silentSince: number | null = null

  const unsubscribe = audio.subscribe((next) => {
    analyser = next
    samples = next ? new Float32Array(next.fftSize) : new Float32Array(0)
  })

  const detectPause = (now: number): void => {
    if (signal.aborted) {
      return
    }
    if (analyser && samples.length > 0) {
      analyser.getFloatTimeDomainData(samples)
      let sumOfSquares = 0
      for (let index = 0; index < samples.length; index += 1) {
        const sample = samples[index] ?? 0
        sumOfSquares += sample * sample
      }
      const rms = Math.sqrt(sumOfSquares / samples.length)

      if (!speaking && rms >= VOICE_ENTER_RMS) {
        speaking = true
        silentSince = null
      } else if (speaking && rms <= VOICE_EXIT_RMS) {
        silentSince ??= now
        if (now - silentSince >= COMMIT_SILENCE_MS) {
          speaking = false
          silentSince = null
          commit()
        }
      } else if (speaking) {
        silentSince = null
      }
    }
    frame = requestAnimationFrame(detectPause)
  }

  frame = requestAnimationFrame(detectPause)
  return () => {
    unsubscribe()
    if (frame !== null) {
      cancelAnimationFrame(frame)
    }
  }
}

export function useRealtimeTranscription(audio: AudioLevelHandle): void {
  const stream = useSessionStore((state) => state.stream)
  const setConnection = useSessionStore((state) => state.setConnection)
  const setTranscriptState = useSessionStore((state) => state.setTranscriptState)
  const setIntent = useSessionStore((state) => state.setIntent)

  useEffect(() => {
    if (!stream) {
      setConnection('idle')
      return
    }

    const controller = new AbortController()
    const peer = new RTCPeerConnection()
    const events = peer.createDataChannel('oai-events')
    let backend: WebSocket | null = null
    let stopPcmStream: (() => void) | null = null
    let stopManualCommit: (() => void) | null = null
    let providerTranscriptionSeen = false
    const existingSegments = useSessionStore.getState().transcriptSegments
    let nextItemOrder = existingSegments.length
    const transcriptItems = new Map<string, TranscriptItem>(
      existingSegments.map((segment, order) => [
        segment.itemId,
        { order, text: segment.text, complete: segment.complete },
      ]),
    )
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

    /**
     * Every client-to-server message the live path can produce goes through here.
     *
     * Live discovery is a credit control, so it gates at the call site rather than in a render:
     * settled speech that never reaches the backend never reaches the distiller gate, and a query
     * that is never made cannot spend a Cala credit. The setting is read at send time so flipping
     * it takes effect on the next word instead of on the next reconnect.
     */
    const relay = (message: ClientMessage): void => {
      if (!backend || !useSettings.getState().liveDiscovery) {
        return
      }
      send(backend, message)
    }

    /** Paint a message the browser has decided not to send. */
    const paintLocally = (message: ClientMessage): void => {
      if (message.type === 'transcript.delta') {
        updateTranscriptItem(
          message.item_id,
          message.delta,
          false,
          (current, delta) => current + delta,
        )
      } else if (message.type === 'transcript.completed') {
        updateTranscriptItem(
          message.item_id,
          message.transcript,
          true,
          (_current, transcript) => transcript,
        )
      }
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
      if (!message || typeof message.type !== 'string') {
        return
      }
      if (message.type === 'error') {
        const providerError = isRecord(message.error) ? message.error : null
        const detail =
          providerError && typeof providerError.message === 'string'
            ? providerError.message
            : 'OpenAI rejected the live transcription session.'
        setConnection('error', detail)
        return
      }
      if (typeof message.item_id !== 'string') {
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
        relay({
          type: 'transcript.delta',
          event_id: providerEventId,
          item_id: message.item_id,
          delta: message.delta,
        })
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
        relay({
          type: 'transcript.completed',
          event_id: providerEventId,
          item_id: message.item_id,
          transcript: message.transcript,
        })
      }
    })
    events.addEventListener('open', () => {
      // gpt-live-transcribe rejects server and semantic VAD, and its transcription buffer is not
      // populated by Safari's RTP track. Append explicit 24 kHz PCM over the same data channel,
      // then commit only after the local analyser has observed a real phrase and pause.
      stopPcmStream = startPcmStream(stream, events, controller.signal)
      stopManualCommit = startManualCommitLoop(
        audio,
        () => events.send(JSON.stringify({ type: 'input_audio_buffer.commit' })),
        controller.signal,
      )
      setConnection('connected')
    })
    events.addEventListener('error', () =>
      setConnection('error', 'The live transcription channel failed.'),
    )
    peer.addEventListener('connectionstatechange', () => {
      if (peer.connectionState === 'failed') {
        setConnection('error', 'The live audio connection failed.')
      }
    })

    for (const track of stream.getAudioTracks()) {
      // Transcription sessions never send audio back. Declaring the media section as send-only is
      // important in Safari and avoids negotiating a receive path the provider cannot fulfil.
      peer.addTransceiver(track, { direction: 'sendonly', streams: [stream] })
    }

    async function connect(): Promise<void> {
      try {
        backend = await openBackendSocket(controller.signal, onBackendMessage)
        let token: RealtimeTokenResponse
        try {
          token = await fetchToken(controller.signal, useSettings.getState().language)
        } catch (error) {
          if (error instanceof RealtimeProviderError && error.code === 'realtime_not_configured') {
            setConnection('connected')
            await playFixture(controller.signal, (message) => {
              if (useSettings.getState().liveDiscovery) {
                relay(message)
                return
              }
              // In fixture mode the backend echo is the only thing that paints. With discovery
              // off nothing may leave the browser, so the words land here instead of nowhere.
              paintLocally(message)
            })
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
      stopPcmStream?.()
      stopManualCommit?.()
      events.close()
      peer.close()
      backend?.close()
    }
  }, [audio, setConnection, setIntent, setTranscriptState, stream])
}
