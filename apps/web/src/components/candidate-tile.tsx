import type { Candidate } from '@glia/api-client'
import { type CSSProperties, useState } from 'react'
import { cn } from '@/lib/utils'

interface CandidateTileProps {
  candidate: Candidate
  /** Position in the grid, driving the staggered entry. */
  index: number
  onUnavailable: (id: string) => void
}

/** Fallback shape for a candidate the backend could not measure. */
const FALLBACK_ASPECT = 4 / 3

/**
 * The aspect ratio the tile reserves before a single byte of the image has loaded.
 *
 * This is the whole reason `width` and `height` travel on the contract. The box is sized
 * from numbers, the image fades into a box that is already the right shape, and nothing
 * below it moves when a wave of thirty lands.
 */
function aspectOf(candidate: Candidate): number {
  const { width, height } = candidate
  if (typeof width !== 'number' || typeof height !== 'number' || width <= 0 || height <= 0) {
    return FALLBACK_ASPECT
  }
  return width / height
}

/**
 * One image in the grid.
 *
 * Everything here is text from a source we do not control. `title` and `licence` are
 * rendered as React children — plain text nodes, never `dangerouslySetInnerHTML` — so
 * markup in a Commons file description shows up as the characters it is.
 */
export function CandidateTile({ candidate, index, onUnavailable }: CandidateTileProps) {
  const [loaded, setLoaded] = useState(false)
  const cited = candidate.lane === 'cited'

  return (
    <figure
      // The stagger index is capped: a wave of thirty must not make the last tile wait a
      // second and a half to appear.
      style={{ '--candidate-index': Math.min(index, 11) } as CSSProperties}
      className="candidate-tile"
    >
      <a
        href={candidate.source_url}
        target="_blank"
        rel="noreferrer noopener"
        className="candidate-tile-frame"
        // Reserved before load. `aspect-ratio` on the frame means the browser knows this
        // tile's height from the first paint, so the grid never reflows around it.
        style={{ aspectRatio: aspectOf(candidate) }}
      >
        <img
          // Exactly what the backend sent. It is already routed through `/api/image`, and
          // rebuilding it here would route around the proxy's allowlist and byte cap.
          src={candidate.image_url}
          alt={candidate.title ?? 'Discovered image'}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          draggable={false}
          className={cn('candidate-tile-image', loaded && 'is-loaded')}
          onLoad={() => setLoaded(true)}
          // A 404, a blocked host or a proxy refusal all land here. A tile that cannot
          // show an image is not a tile, so it takes itself out rather than leaving a
          // reserved hole in the grid.
          onError={() => onUnavailable(candidate.id)}
        />
        <span className={cn('candidate-badge', cited ? 'is-cited' : 'is-open')}>
          {cited ? 'CITED' : 'OPEN'}
        </span>
      </a>
      <figcaption className="candidate-tile-caption">
        <span className="candidate-tile-title">
          {candidate.title ?? candidate.publisher ?? '—'}
        </span>
        {candidate.licence ? (
          <span className="candidate-tile-licence">{candidate.licence}</span>
        ) : null}
      </figcaption>
    </figure>
  )
}
