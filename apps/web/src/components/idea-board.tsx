import { Pin } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { type PinnedRef, useSessionStore } from '@/stores/session'

/**
 * The placeholder reference board: six hand-drawn stickers that reveal as the transcript grows,
 * each pinnable, each badged `demo` because none of them came from anywhere.
 *
 * Moved out of `workpane.tsx` intact rather than deleted. The workpane now leads with what Cala
 * actually cited, and this stands in for the image lane that does not exist yet — Wikimedia and
 * Openverse (Lane B) plus images extracted from the pages Cala cites (Lane A) replace it. The
 * `demo` badge is load-bearing until then: nothing here is sourced, and the UI must not imply
 * that it is.
 *
 * Pinning is no longer local state. A pin is a conditioning input for Generate, so it belongs to
 * the session rather than to this component — the rail and the backend both read it from there.
 */

interface IdeaBoardProps {
  className?: string | undefined
}

interface StickerSpec {
  id: string
  title: string
  lane: 'cited page' | 'open'
  variant: number
}

const STICKERS: StickerSpec[] = [
  { id: 'observatory', title: 'Cobalt observatory', lane: 'cited page', variant: 0 },
  { id: 'brutalist-sun', title: 'Brutalist sun study', lane: 'open', variant: 1 },
  { id: 'quiet-coast', title: 'Quiet Mediterranean', lane: 'open', variant: 2 },
  { id: 'red-editorial', title: 'Red editorial forms', lane: 'cited page', variant: 3 },
  { id: 'night-arch', title: 'Night architecture', lane: 'open', variant: 4 },
  { id: 'blue-type', title: 'Blue type fragment', lane: 'cited page', variant: 5 },
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

export function IdeaBoard({ className }: IdeaBoardProps) {
  const transcript = useSessionStore((state) => state.transcript)
  const setProcessedWordCount = useSessionStore((state) => state.setProcessedWordCount)
  const pinned = useSessionStore((state) => state.pinned)
  const togglePin = useSessionStore((state) => state.togglePin)
  const [revealedCount, setRevealedCount] = useState(0)
  const wordCount = transcript.trim() ? transcript.trim().split(/\s+/).length : 0
  const suggestedCount =
    wordCount < 3 ? 0 : Math.min(STICKERS.length, Math.ceil((wordCount - 2) / 3) * 2)

  useEffect(() => {
    if (suggestedCount <= revealedCount) {
      return
    }
    setRevealedCount(suggestedCount)
    setProcessedWordCount(wordCount)
  }, [revealedCount, setProcessedWordCount, suggestedCount, wordCount])

  // A sticker is inline SVG with no URL of any kind, so both URLs pin as null. There is no
  // origin file for the server to fetch and re-host; the honest consequence is that this pin
  // steers the prompt through its title and is not counted as a reference image.
  const refFor = (sticker: StickerSpec): PinnedRef => ({
    id: sticker.id,
    title: sticker.title,
    lane: sticker.lane,
    imageUrl: null,
    originImageUrl: null,
    sourceUrl: null,
  })

  return (
    <section
      aria-label="Evolving visual references"
      className={cn('idea-board min-h-0 overflow-hidden p-3 md:p-6', className)}
    >
      {STICKERS.slice(0, revealedCount).map((sticker, index) => {
        const isPinned = pinned.some((pin) => pin.id === sticker.id)
        return (
          <figure
            className={cn('idea-sticker', `idea-sticker--${index + 1}`, isPinned && 'is-pinned')}
            key={sticker.id}
          >
            <div className="sticker-art">
              <StickerArt variant={sticker.variant} />
            </div>
            <figcaption className="sr-only">{sticker.title}</figcaption>
            <span className="sticker-lane">demo · {sticker.lane}</span>
            <button
              type="button"
              className="pin-button"
              aria-label={`${isPinned ? 'Unpin' : 'Pin'} ${sticker.title}`}
              aria-pressed={isPinned}
              onClick={() => togglePin(refFor(sticker))}
            >
              <Pin aria-hidden="true" strokeWidth={1.8} />
            </button>
          </figure>
        )
      })}
    </section>
  )
}
