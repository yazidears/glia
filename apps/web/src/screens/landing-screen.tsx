import { Mic, Pin } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useMicrophone } from '@/hooks/use-microphone'
import { useRealtimeTranscription } from '@/hooks/use-realtime-transcription'
import { cn } from '@/lib/utils'
import { type MicState, useSessionStore } from '@/stores/session'

const CAPTIONS: Record<MicState, string> = {
  idle: 'Start speaking',
  requesting: 'Allow microphone',
  granted: 'Listening',
  denied: 'Try microphone again',
  unsupported: 'Microphone unavailable',
}

interface StickerSpec {
  id: string
  title: string
  source: string
  lane: 'cited page' | 'open'
  variant: number
}

const STICKERS: StickerSpec[] = [
  {
    id: 'observatory',
    title: 'Cobalt observatory',
    source: 'Demo source',
    lane: 'cited page',
    variant: 0,
  },
  {
    id: 'brutalist-sun',
    title: 'Brutalist sun study',
    source: 'Demo source',
    lane: 'open',
    variant: 1,
  },
  {
    id: 'quiet-coast',
    title: 'Quiet Mediterranean',
    source: 'Demo source',
    lane: 'open',
    variant: 2,
  },
  {
    id: 'red-editorial',
    title: 'Red editorial forms',
    source: 'Demo source',
    lane: 'cited page',
    variant: 3,
  },
  {
    id: 'night-arch',
    title: 'Night architecture',
    source: 'Demo source',
    lane: 'open',
    variant: 4,
  },
  {
    id: 'blue-type',
    title: 'Blue type fragment',
    source: 'Demo source',
    lane: 'cited page',
    variant: 5,
  },
]

function StickerArt({ variant }: { variant: number }) {
  if (variant === 0) {
    return (
      <svg aria-hidden="true" viewBox="0 0 320 240">
        <rect width="320" height="240" fill="#3159d7" />
        <circle cx="250" cy="48" r="25" fill="#f5f0d6" />
        <path d="M0 164C68 146 120 171 176 155s91-4 144-22v107H0Z" fill="#779be7" />
        <path d="M0 191c74-20 142 12 202-8 43-14 76-11 118-24v81H0Z" fill="#c2d0f2" />
        <path d="M90 80h104v89H90z" fill="#17255f" />
        <path d="m78 80 64-44 64 44Z" fill="#d2d9ec" />
        <circle cx="142" cy="38" r="18" fill="#17255f" />
        <rect x="136" y="20" width="12" height="31" fill="#d2d9ec" />
        <rect x="106" y="105" width="24" height="64" fill="#f2c35e" />
      </svg>
    )
  }
  if (variant === 1) {
    return (
      <svg aria-hidden="true" viewBox="0 0 320 240">
        <rect width="320" height="240" fill="#e9e2d4" />
        <circle cx="239" cy="63" r="46" fill="#f25d35" />
        <rect x="35" y="36" width="92" height="166" fill="#171717" />
        <rect x="61" y="64" width="40" height="70" fill="#e9e2d4" />
        <path d="M126 107h94v95h-94z" fill="#b4aa97" />
        <path d="m220 107 61 95h-61Z" fill="#314fd1" />
        <path d="M126 107h94l-47-48Z" fill="#f6c85e" />
      </svg>
    )
  }
  if (variant === 2) {
    return (
      <svg aria-hidden="true" viewBox="0 0 320 240">
        <rect width="320" height="240" fill="#c9e9ef" />
        <rect y="126" width="320" height="114" fill="#4f8c9a" />
        <path d="M0 148c57-26 91 18 146-2s108 20 174-4v98H0Z" fill="#8cc8cc" />
        <circle cx="72" cy="58" r="30" fill="#fff8de" />
        <path d="M224 97h41l17 73h-74Z" fill="#df4b3f" />
        <rect x="232" y="84" width="24" height="89" fill="#302d2b" />
        <path d="M210 174h74v13h-74z" fill="#302d2b" />
        <path d="M38 123c26-33 58-38 92 0Z" fill="#315d53" />
      </svg>
    )
  }
  if (variant === 3) {
    return (
      <svg aria-hidden="true" viewBox="0 0 320 240">
        <rect width="320" height="240" fill="#f0eee6" />
        <path d="M-19 17h153v67H-19z" fill="#d83b31" transform="rotate(-8 57 50)" />
        <circle cx="231" cy="80" r="57" fill="#161616" />
        <path d="m134 104 86-31v144h-86Z" fill="#f6c651" />
        <path d="M17 126h96v87H17z" fill="#3157cf" />
        <path d="m205 168 92-50v99h-92Z" fill="#d83b31" />
        <circle cx="66" cy="170" r="20" fill="#f0eee6" />
      </svg>
    )
  }
  if (variant === 4) {
    return (
      <svg aria-hidden="true" viewBox="0 0 320 240">
        <rect width="320" height="240" fill="#10131b" />
        <circle cx="70" cy="56" r="25" fill="#f1c65b" />
        <path d="M73 240V99c0-43 34-76 77-76s77 33 77 76v141Z" fill="#314b73" />
        <path d="M105 240V105c0-25 20-46 45-46s45 21 45 46v135Z" fill="#8aa3bd" />
        <rect x="133" y="119" width="34" height="121" fill="#10131b" />
        <path d="M0 207h320v33H0z" fill="#262b37" />
      </svg>
    )
  }
  return (
    <svg aria-hidden="true" viewBox="0 0 320 240">
      <rect width="320" height="240" fill="#3559d6" />
      <path d="M32 28h256v184H32z" fill="#e8e5dc" />
      <path d="M65 64h190v20H65zm0 36h137v20H65zm0 36h165v20H65z" fill="#171717" />
      <path d="M216 98h39v86h-39z" fill="#f06445" />
      <circle cx="86" cy="185" r="26" fill="#f3c65b" />
      <path d="m121 169 67 43h-67Z" fill="#3559d6" />
    </svg>
  )
}

function AnimatedDots() {
  return (
    <span aria-hidden="true" className="listening-dots">
      <span />
      <span />
      <span />
    </span>
  )
}

export function LandingScreen() {
  const { micState, toggle } = useMicrophone()
  useRealtimeTranscription()
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(() => new Set())
  const [revealedStickerCount, setRevealedStickerCount] = useState(0)
  const [processedWordCount, setProcessedWordCount] = useState(0)
  const connectionState = useSessionStore((state) => state.connectionState)
  const transcript = useSessionStore((state) => state.transcript)
  const transcriptSegments = useSessionStore((state) => state.transcriptSegments)
  const isListening = micState === 'granted'
  const hasWorkspace = isListening || transcriptSegments.length > 0
  const transcriptWordCount = transcript.trim() ? transcript.trim().split(/\s+/).length : 0
  const suggestedStickerCount =
    transcriptWordCount < 3
      ? 0
      : Math.min(STICKERS.length, Math.ceil((transcriptWordCount - 2) / 3) * 2)
  const visibleStickers = hasWorkspace ? STICKERS.slice(0, revealedStickerCount) : []
  const transcriptWords = [...transcript.matchAll(/\S+\s*/g)].map((match) => ({
    text: match[0],
    offset: match.index,
  }))
  const completedWordCount = transcriptSegments
    .filter((segment) => segment.complete)
    .reduce((count, segment) => count + (segment.text.match(/\S+/g)?.length ?? 0), 0)
  const blackWordCount = Math.max(processedWordCount, completedWordCount)
  const caption =
    connectionState === 'connecting'
      ? 'Connecting'
      : connectionState === 'error'
        ? 'Connection interrupted'
        : !isListening && hasWorkspace
          ? 'Continue speaking'
          : CAPTIONS[micState]

  useEffect(() => {
    if (suggestedStickerCount <= revealedStickerCount) {
      return
    }
    setRevealedStickerCount(suggestedStickerCount)
    setProcessedWordCount(transcriptWordCount)
  }, [revealedStickerCount, suggestedStickerCount, transcriptWordCount])

  const togglePin = (id: string): void => {
    setPinnedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  return (
    <main className="glia-canvas" data-workspace={hasWorkspace}>
      <header className="glia-header">
        <a className="glia-wordmark" href="/" aria-label="Glia home">
          glia
        </a>
      </header>

      <section className="intro-copy" data-hidden={hasWorkspace} aria-hidden={hasWorkspace}>
        <p className="intro-kicker">Speak until you see it.</p>
        <h1>Speak your mind.</h1>
        <p className="intro-description">
          Describe the image you can feel but cannot quite prompt.
        </p>
      </section>

      <section
        className="idea-board"
        data-visible={hasWorkspace}
        aria-label="Evolving visual references"
      >
        {visibleStickers.map((sticker, index) => {
          const isPinned = pinnedIds.has(sticker.id)
          return (
            <figure
              className={cn('idea-sticker', `idea-sticker--${index + 1}`, isPinned && 'is-pinned')}
              key={sticker.id}
            >
              <div className="sticker-art">
                <StickerArt variant={sticker.variant} />
              </div>
              <figcaption>
                <span>{sticker.title}</span>
                <small>
                  <span className="sticker-source">{sticker.source} · </span>
                  <span className="sticker-lane">{sticker.lane}</span>
                </small>
              </figcaption>
              <button
                type="button"
                className="pin-button"
                aria-label={`${isPinned ? 'Unpin' : 'Pin'} ${sticker.title}`}
                aria-pressed={isPinned}
                onClick={() => togglePin(sticker.id)}
              >
                <Pin aria-hidden="true" strokeWidth={1.8} />
              </button>
            </figure>
          )
        })}
      </section>

      <section
        className="transcript-panel"
        data-visible={hasWorkspace}
        aria-live="polite"
        aria-label="Live transcript"
      >
        {transcriptSegments.length > 0 ? (
          <p className="transcript-copy">
            {transcriptWords.map((word, index) => (
              <span
                className={
                  index < blackWordCount ? 'transcript-confirmed' : 'transcript-provisional'
                }
                key={word.offset}
              >
                {word.text}
              </span>
            ))}
          </p>
        ) : (
          <p className="speak-now">
            Speak now.
            <AnimatedDots />
          </p>
        )}
      </section>

      <Button
        type="button"
        variant="outline"
        onClick={toggle}
        aria-label={`${caption}. ${isListening ? 'Stop listening' : 'Start listening'}`}
        aria-pressed={isListening}
        className="voice-control"
        data-workspace={hasWorkspace}
        data-listening={isListening}
        data-error={micState === 'denied' || micState === 'unsupported'}
      >
        <span className="voice-orb">
          <Mic aria-hidden="true" strokeWidth={1.8} />
        </span>
        <span className="voice-label">
          <strong>{caption}</strong>
        </span>
      </Button>
    </main>
  )
}
