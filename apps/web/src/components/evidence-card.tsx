import type { EvidenceItem, EvidenceOrigin } from '@glia/api-client'
import { motion, type Transition } from 'motion/react'
import { useState } from 'react'
import { cn } from '@/lib/utils'

/**
 * One piece of quoted evidence and where it came from.
 *
 * The quote-plus-origin pairing is the whole argument the screen makes: the answer is not a
 * model's recollection, it is these sentences from these publications. So the quote is set as
 * the primary text and the publisher sits directly beneath it, close enough to read as one
 * unit rather than as body copy with a footnote.
 *
 * Every string here — quote, publisher, document title — comes from a host we do not control.
 * All of it is rendered as text. No favicons, no logos: fetching a third-party image to
 * decorate a citation is a tracking pixel, so the publisher is its name.
 */

/**
 * How much of a card is shown before it asks. Live Cala responses are not tidy: a single
 * `context[]` item came back as a 300-word scraped blob carrying 26 origins, which buries the
 * publisher line the card exists to show. Collapsing is a reading decision, not a claim about
 * the data — the count is always named and the full text is one click away, never dropped.
 */
const COLLAPSED_ORIGINS = 2

interface OriginLineProps {
  origin: EvidenceOrigin
}

function OriginLine({ origin }: OriginLineProps) {
  const publisher = origin.source?.name?.trim()
  const title = origin.document?.name?.trim()
  const url = origin.document?.url ?? null
  // A link with nothing to name is not a citation. Without a title or a publisher there is
  // nothing honest to render, so nothing is.
  if (!publisher && !title) {
    return null
  }

  return (
    <div className="flex flex-col gap-0.5">
      {publisher ? (
        <span className="font-medium text-[11px] text-neutral-500 uppercase tracking-[0.08em] dark:text-neutral-400">
          {publisher}
        </span>
      ) : null}
      {title ? (
        url ? (
          <a
            href={url}
            target="_blank"
            rel="noreferrer noopener"
            className="w-fit text-neutral-700 text-sm underline decoration-neutral-300 underline-offset-[3px] transition-colors hover:text-neutral-950 hover:decoration-neutral-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:text-neutral-300 dark:decoration-neutral-700 dark:hover:text-neutral-50"
          >
            {title}
          </a>
        ) : (
          <span className="text-neutral-700 text-sm dark:text-neutral-300">{title}</span>
        )
      ) : null}
    </div>
  )
}

interface EvidenceCardProps {
  item: EvidenceItem
  transition: Transition
}

export function EvidenceCard({ item, transition }: EvidenceCardProps) {
  const [expanded, setExpanded] = useState(false)

  // Deduped by identity rather than position: the same document cited twice is one citation,
  // and the resulting key is stable without falling back to an array index.
  const origins = new Map<string, EvidenceOrigin>()
  for (const origin of item.origins) {
    const key = origin.document?.url ?? origin.document?.name ?? origin.source?.name
    if (key && !origins.has(key)) {
      origins.set(key, origin)
    }
  }

  const all = [...origins]
  const shown = expanded ? all : all.slice(0, COLLAPSED_ORIGINS)
  const hidden = all.length - shown.length
  const canExpand = hidden > 0 || item.content.length > 320

  return (
    <motion.article
      layout
      transition={transition}
      variants={{
        hidden: { opacity: 0, y: 10 },
        shown: { opacity: 1, y: 0 },
      }}
      className={cn(
        'flex flex-col gap-3 border-l py-1 pl-4',
        // The only differentiation between evidence that carried the answer and evidence that
        // merely came back is the weight of this rule. Server-side ordering does the rest.
        item.carried_answer
          ? 'border-neutral-400 dark:border-neutral-500'
          : 'border-neutral-200 dark:border-neutral-800',
      )}
    >
      {item.carried_answer ? (
        <span className="flex items-center gap-1.5 text-[11px] text-neutral-500 dark:text-neutral-400">
          <span aria-hidden className="size-1 rounded-full bg-neutral-400 dark:bg-neutral-500" />
          Carried the answer
        </span>
      ) : null}

      {item.content ? (
        <p
          className={cn(
            'max-w-[60ch] text-[15px] text-neutral-800 leading-relaxed dark:text-neutral-200',
            !expanded && 'line-clamp-5',
          )}
        >
          {item.content}
        </p>
      ) : null}

      {shown.length > 0 ? (
        <div className="flex flex-col gap-2">
          {shown.map(([key, origin]) => (
            <OriginLine key={key} origin={origin} />
          ))}
        </div>
      ) : null}

      {canExpand ? (
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          className="w-fit rounded text-[11px] text-neutral-500 underline decoration-neutral-300 underline-offset-[3px] transition-colors hover:text-neutral-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:text-neutral-400 dark:decoration-neutral-700 dark:hover:text-neutral-100"
        >
          {expanded
            ? 'Show less'
            : hidden > 0
              ? `Show ${hidden} more source${hidden === 1 ? '' : 's'}`
              : 'Show full quote'}
        </button>
      ) : null}
    </motion.article>
  )
}
