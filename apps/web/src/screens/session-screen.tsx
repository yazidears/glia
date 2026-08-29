import type { ConnectionState } from '@glia/api-client'
import { Mic } from 'lucide-react'
import { type CSSProperties, useCallback, useEffect, useRef, useState } from 'react'
import { CalaEntityRail } from '@/components/cala-entity-rail'
import { EntryLoader } from '@/components/entry-loader'
import { IntentHud } from '@/components/intent-hud'
import { LandingReferenceArc } from '@/components/landing-reference-arc'
import { PinRail } from '@/components/pin-rail'
import { SettingsDialog } from '@/components/settings-dialog'
import { TranscriptList } from '@/components/transcript-list'
import { Waveform } from '@/components/waveform'
import { Workpane } from '@/components/workpane'
import { useAudioLevel } from '@/hooks/use-audio-level'
import { useMicrophone } from '@/hooks/use-microphone'
import { useRealtimeTranscription } from '@/hooks/use-realtime-transcription'
import { useVoiceCommands } from '@/hooks/use-voice-commands'
import { cn } from '@/lib/utils'
import { type MicState, useSessionStore } from '@/stores/session'

const ENTITY_RAIL_PREVIEW = [
  { name: 'Braun', type: 'Company' },
  { name: 'Teenage Engineering', type: 'Company' },
  { name: 'Centre Pompidou', type: 'Facility' },
  { name: 'Jantar Mantar', type: 'WorkOfArt' },
] as const

const CAPTIONS: Record<MicState, string> = {
  idle: 'Start speaking',
  requesting: 'Allow microphone',
  granted: 'Listening',
  denied: 'Try microphone again',
  unsupported: 'Microphone unavailable',
}

function captionFor(micState: MicState, connectionState: ConnectionState): string {
  if (connectionState === 'connecting') {
    return 'Connecting'
  }
  if (connectionState === 'error') {
    return 'Connection interrupted'
  }
  return CAPTIONS[micState]
}

type GenerationTransitionStage = 'idle' | 'gathering' | 'revealing' | 'returning'

interface GenerationFlight {
  id: string
  src: string
  top: number
  left: number
  width: number
  height: number
  deltaX: number
  deltaY: number
  rotation: number
  delay: number
}

interface GenerationSnapshot {
  flights: GenerationFlight[]
  centerX: number
  centerY: number
  surfaceTop: number
  surfaceLeft: number
  surfaceWidth: number
  surfaceHeight: number
}

const EMPTY_GENERATION_SNAPSHOT: GenerationSnapshot = {
  flights: [],
  centerX: 0,
  centerY: 0,
  surfaceTop: 0,
  surfaceLeft: 0,
  surfaceWidth: 0,
  surfaceHeight: 0,
}

function generationSnapshot(): GenerationSnapshot {
  const surface = document.querySelector<HTMLElement>('.idea-board, [aria-label="Generated image"]')
  const surfaceRect = surface?.getBoundingClientRect() ?? {
    top: 0,
    left: window.innerWidth * 0.34,
    width: window.innerWidth * 0.66,
    height: window.innerHeight,
  }
  const centerX = surfaceRect.left + surfaceRect.width * 0.5
  const centerY = surfaceRect.top + surfaceRect.height * 0.48
  const seen = new Set<string>()
  const sources = [
    ...document.querySelectorAll<HTMLImageElement>(
      '.idea-sticker .sticker-art img, .pin-thumb-image, .generated-image',
    ),
  ].filter((image) => {
    const rect = image.getBoundingClientRect()
    const visible = rect.width > 1 && rect.height > 1 && getComputedStyle(image).display !== 'none'
    if (!visible || !image.currentSrc || seen.has(image.currentSrc)) {
      return false
    }
    seen.add(image.currentSrc)
    return true
  })

  return {
    centerX,
    centerY,
    surfaceTop: surfaceRect.top,
    surfaceLeft: surfaceRect.left,
    surfaceWidth: surfaceRect.width,
    surfaceHeight: surfaceRect.height,
    flights: sources.slice(0, 9).map((image, index) => {
      const rect = image.getBoundingClientRect()
      const scale = Math.min(1, 176 / rect.width, 136 / rect.height)
      const width = rect.width * scale
      const height = rect.height * scale
      const left = rect.left + (rect.width - width) / 2
      const top = rect.top + (rect.height - height) / 2
      return {
        id: `${image.currentSrc}-${index}`,
        src: image.currentSrc,
        top,
        left,
        width,
        height,
        deltaX: centerX - (left + width / 2),
        deltaY: centerY - (top + height / 2),
        rotation: ((index % 5) - 2) * 2.4,
        delay: index * 42,
      }
    }),
  }
}

function flightStyle(flight: GenerationFlight): CSSProperties {
  return {
    top: `${flight.top}px`,
    left: `${flight.left}px`,
    width: `${flight.width}px`,
    height: `${flight.height}px`,
    '--generation-dx': `${flight.deltaX}px`,
    '--generation-dy': `${flight.deltaY}px`,
    '--generation-rotation': `${flight.rotation}deg`,
    '--generation-delay': `${flight.delay}ms`,
  } as CSSProperties
}

/**
 * One spatial bridge between the reference board and the fal result.
 *
 * The source rectangles are sampled once, when Generate starts. Their visual clones move on the
 * compositor while the real board and pin state stay untouched underneath. The veil only leaves
 * after the result image has decoded, so a fast request cannot produce a white flash and a slow
 * one never pretends to be finished.
 */
function GenerationTransition() {
  const status = useSessionStore((state) => state.generationStatus)
  const imageReady = useSessionStore((state) => state.generationImageReady)
  const pinnedCount = useSessionStore((state) => state.pinned.length)
  const [stage, setStage] = useState<GenerationTransitionStage>('idle')
  const [snapshot, setSnapshot] = useState<GenerationSnapshot>(EMPTY_GENERATION_SNAPSHOT)
  const [directionCount, setDirectionCount] = useState(0)
  const previousStatus = useRef(status)

  useEffect(() => {
    const wasGenerating = previousStatus.current === 'generating'
    previousStatus.current = status
    if (status !== 'generating' || wasGenerating) {
      return
    }
    const frame = window.requestAnimationFrame(() => {
      setSnapshot(generationSnapshot())
      setDirectionCount(pinnedCount)
      setStage('gathering')
    })
    return () => window.cancelAnimationFrame(frame)
  }, [pinnedCount, status])

  useEffect(() => {
    if (stage === 'idle' || status === 'generating') {
      return
    }
    if (status === 'error' && stage !== 'returning') {
      setStage('returning')
      return
    }
    if (status === 'ready' && imageReady && stage !== 'revealing') {
      setStage('revealing')
      return
    }
    if (stage !== 'returning' && stage !== 'revealing') {
      return
    }
    const timeout = window.setTimeout(() => setStage('idle'), stage === 'revealing' ? 520 : 300)
    return () => window.clearTimeout(timeout)
  }, [imageReady, stage, status])

  if (stage === 'idle') {
    return null
  }

  const overlayStyle = {
    '--generation-center-x': `${snapshot.centerX}px`,
    '--generation-center-y': `${snapshot.centerY}px`,
    '--generation-surface-top': `${snapshot.surfaceTop}px`,
    '--generation-surface-left': `${snapshot.surfaceLeft}px`,
    '--generation-surface-width': `${snapshot.surfaceWidth}px`,
    '--generation-surface-height': `${snapshot.surfaceHeight}px`,
  } as CSSProperties
  const message =
    status === 'error'
      ? 'Generation stopped'
      : status === 'ready' && !imageReady
        ? 'Loading the final image'
        : 'Composing your image'
  const kicker =
    status === 'error'
      ? 'fal · stopped'
      : status === 'ready'
        ? 'fal · complete'
        : 'fal · generating'

  return (
    <div
      aria-live="polite"
      className="generation-transition"
      data-stage={stage}
      role="status"
      style={overlayStyle}
    >
      <div aria-hidden="true" className="generation-veil" />
      {snapshot.flights.map((flight) => (
        <div
          aria-hidden="true"
          className="generation-flight"
          key={flight.id}
          style={flightStyle(flight)}
        >
          <img alt="" draggable="false" src={flight.src} />
        </div>
      ))}
      <div aria-hidden="true" className="generation-energy" />
      <div className="generation-status-copy">
        <span className="generation-status-kicker">{kicker}</span>
        <strong>{message}</strong>
        <span>
          {directionCount > 0
            ? `${directionCount} pinned ${directionCount === 1 ? 'direction' : 'directions'}`
            : 'Your conversation is the direction'}
        </span>
      </div>
    </div>
  )
}

export function SessionScreen() {
  const [isBooting, setIsBooting] = useState(true)
  const { micState, toggle } = useMicrophone()
  const audio = useAudioLevel()
  useRealtimeTranscription(audio)
  useVoiceCommands()
  const phase = useSessionStore((state) => state.phase)
  const connectionState = useSessionStore((state) => state.connectionState)
  const entityRailPreview =
    import.meta.env.DEV &&
    new URLSearchParams(window.location.search).get('preview') === 'cala-rail'
  const isSession = phase === 'session' || entityRailPreview
  const isListening = micState === 'granted'
  const caption = captionFor(micState, connectionState)
  const finishBoot = useCallback(() => setIsBooting(false), [])

  useEffect(() => {
    document.title = 'Glia'
  }, [])

  return (
    <main className="session-canvas" data-session={isSession}>
      <a className="glia-wordmark" href="/" aria-label="Glia home">
        glia
      </a>

      <SettingsDialog />

      <LandingReferenceArc hidden={isSession} />

      {isBooting ? <EntryLoader onComplete={finishBoot} /> : null}

      <section
        className="session-hero"
        data-hidden={isSession || isBooting}
        aria-hidden={isSession || isBooting}
      >
        <p>Speak until you see it.</p>
        <h1>Speak your mind.</h1>
        <p>Describe the image you can feel but cannot quite prompt.</p>
      </section>

      {isSession ? (
        <div className="session-workspace">
          <section className="transcript-column">
            <div className="transcript-scroll">
              <TranscriptList />
            </div>
          </section>
          <Workpane />
          <IntentHud />
          <GenerationTransition />
        </div>
      ) : null}

      {/* Absent at zero pins, and it renders itself away — see `PinRail`. */}
      {isSession ? (
        <>
          <CalaEntityRail
            previewSuggestions={entityRailPreview ? ENTITY_RAIL_PREVIEW : undefined}
          />
          <PinRail />
        </>
      ) : null}

      <button
        type="button"
        onClick={toggle}
        aria-pressed={isListening}
        aria-label={`${caption}. ${isListening ? 'Stop listening' : 'Start listening'}`}
        className={cn('session-mic', isListening && 'is-listening')}
        data-docked={isSession}
        data-booting={isBooting}
        disabled={isBooting}
      >
        <span className="session-mic-orb">
          <Mic
            aria-hidden="true"
            className={cn(micState === 'requesting' && 'animate-pulse opacity-50')}
            strokeWidth={1.8}
          />
        </span>
        <Waveform active={isListening} handle={audio} variant={isSession ? 'dock' : 'hero'} />
      </button>
    </main>
  )
}
