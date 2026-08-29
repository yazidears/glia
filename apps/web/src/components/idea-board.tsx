import type { Candidate } from '@glia/api-client'
import { Pin } from 'lucide-react'
import { useEffect, useState } from 'react'
import { flushSync } from 'react-dom'
import {
  candidateToPinnedRef,
  DEMO_STICKERS,
  demoRevealCount,
  demoStickerToPinnedRef,
  IDEA_BOARD_PAGE_SIZE,
} from '@/lib/pinned-references'
import { cn } from '@/lib/utils'
import { type PinnedRef, useSessionStore } from '@/stores/session'

/**
 * The live reference board. Real discovery candidates take priority; the six hand-drawn stickers
 * remain only as an explicitly badged fixture fallback.
 *
 * Pinning belongs to the session because a pin is a Generate conditioning input. The conversion
 * helper preserves both the display URL and the origin URL needed by the backend, while fixture
 * stickers honestly carry neither.
 */

interface IdeaBoardProps {
  className?: string | undefined
}

function CandidateSticker({
  candidate,
  index,
  onToggle,
  onUnavailable,
}: {
  candidate: Candidate
  index: number
  onToggle: (source: HTMLElement) => void
  onUnavailable: (id: string) => void
}) {
  const title = candidate.title ?? candidate.publisher ?? 'Visual reference'
  return (
    <figure className={cn('idea-sticker', `idea-sticker--${index + 1}`)}>
      <button
        type="button"
        className="sticker-art sticker-select"
        aria-label={`Pin ${title}`}
        onClick={(event) => onToggle(event.currentTarget)}
      >
        <img
          alt=""
          decoding="async"
          loading="lazy"
          referrerPolicy="no-referrer"
          src={candidate.image_url}
          onError={() => onUnavailable(candidate.id)}
        />
      </button>
      <figcaption className="sr-only">{title}</figcaption>
      <span className="sticker-lane">
        {candidate.lane} · {candidate.publisher ?? 'open corpus'}
      </span>
      <button
        type="button"
        className="pin-button"
        aria-label={`Pin ${title}`}
        aria-pressed="false"
        onClick={(event) => {
          const source = event.currentTarget
            .closest('figure')
            ?.querySelector<HTMLElement>('.sticker-select')
          onToggle(source ?? event.currentTarget)
        }}
      >
        <Pin aria-hidden="true" strokeWidth={1.8} />
      </button>
    </figure>
  )
}

function pinDestination(id: string): HTMLElement | null {
  return (
    [...document.querySelectorAll<HTMLElement>('[data-pin-id]')].find(
      (element) => element.dataset.pinId === id,
    ) ?? null
  )
}

/** Shared-element flight: the board image supplies the start, and the real rail tile is the end. */
function flyToPinRail(source: HTMLElement, pinId: string, pin: () => void): void {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    pin()
    return
  }

  const start = source.getBoundingClientRect()
  const flight = source.cloneNode(true) as HTMLElement
  flight.className = 'pin-flight'
  flight.setAttribute('aria-hidden', 'true')
  Object.assign(flight.style, {
    top: `${start.top}px`,
    left: `${start.left}px`,
    width: `${start.width}px`,
    height: `${start.height}px`,
  })
  document.body.append(flight)

  flushSync(pin)
  requestAnimationFrame(() => {
    const destination = pinDestination(pinId)
    if (!destination) {
      flight.remove()
      return
    }
    const end = destination.getBoundingClientRect()
    const easing =
      getComputedStyle(document.documentElement).getPropertyValue('--ease-in-out').trim() ||
      'cubic-bezier(0.77, 0, 0.175, 1)'
    const animation = flight.animate(
      [
        { opacity: 1, transform: 'translate3d(0, 0, 0) scale(1)' },
        {
          opacity: 0.92,
          transform: `translate3d(${end.left - start.left}px, ${end.top - start.top}px, 0) scale(${end.width / start.width})`,
        },
      ],
      { duration: 240, easing, fill: 'forwards' },
    )
    void animation.finished.then(
      () => flight.remove(),
      () => flight.remove(),
    )
  })
}

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

export function IdeaBoard({ className }: IdeaBoardProps) {
  const transcript = useSessionStore((state) => state.transcript)
  const intentUpdate = useSessionStore((state) => state.intentUpdate)
  const candidates = useSessionStore((state) => state.candidates)
  const setProcessedWordCount = useSessionStore((state) => state.setProcessedWordCount)
  const pinned = useSessionStore((state) => state.pinned)
  const togglePin = useSessionStore((state) => state.togglePin)
  const removeCandidate = useSessionStore((state) => state.removeCandidate)
  const [revealedCount, setRevealedCount] = useState(0)
  const wordCount = transcript.trim() ? transcript.trim().split(/\s+/).length : 0
  const suggestedCount = demoRevealCount(wordCount)
  const pinnedIds = new Set(pinned.map((pin) => pin.id))
  const visibleCandidates = candidates
    .filter((candidate) => !pinnedIds.has(candidate.id))
    .slice(0, IDEA_BOARD_PAGE_SIZE)
  const visibleStickers = DEMO_STICKERS.filter((sticker) => !pinnedIds.has(sticker.id)).slice(
    0,
    revealedCount,
  )

  useEffect(() => {
    if (suggestedCount <= revealedCount) {
      return
    }
    setRevealedCount(suggestedCount)
    setProcessedWordCount(wordCount)
  }, [revealedCount, setProcessedWordCount, suggestedCount, wordCount])

  const pinFrom = (source: HTMLElement, ref: PinnedRef): void => {
    flyToPinRail(source, ref.id, () => togglePin(ref))
  }

  return (
    <section
      aria-label="Evolving visual references"
      className={cn('idea-board min-h-0 overflow-hidden p-3 md:p-6', className)}
    >
      {candidates.length > 0
        ? visibleCandidates.map((candidate, index) => (
            <CandidateSticker
              candidate={candidate}
              index={index}
              key={candidate.id}
              onUnavailable={removeCandidate}
              onToggle={(source) => pinFrom(source, candidateToPinnedRef(candidate))}
            />
          ))
        : intentUpdate?.source === 'fixture'
          ? visibleStickers.map((sticker, index) => (
              <figure className={cn('idea-sticker', `idea-sticker--${index + 1}`)} key={sticker.id}>
                <button
                  type="button"
                  className="sticker-art sticker-select"
                  aria-label={`Pin ${sticker.title}`}
                  onClick={(event) => pinFrom(event.currentTarget, demoStickerToPinnedRef(sticker))}
                >
                  <StickerArt variant={sticker.variant} />
                </button>
                <figcaption className="sr-only">{sticker.title}</figcaption>
                <span className="sticker-lane">demo · {sticker.lane}</span>
                <button
                  type="button"
                  className="pin-button"
                  aria-label={`Pin ${sticker.title}`}
                  aria-pressed="false"
                  onClick={(event) => {
                    const source = event.currentTarget
                      .closest('figure')
                      ?.querySelector<HTMLElement>('.sticker-select')
                    pinFrom(source ?? event.currentTarget, demoStickerToPinnedRef(sticker))
                  }}
                >
                  <Pin aria-hidden="true" strokeWidth={1.8} />
                </button>
              </figure>
            ))
          : null}
    </section>
  )
}
