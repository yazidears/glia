import type { DiscoverResponse, ResolvedEntity } from '@glia/api-client'
import type { CSSProperties } from 'react'
import Markdown, { type Components } from 'react-markdown'
import { CandidateGrid } from '@/components/candidate-grid'
import { EvidenceCard } from '@/components/evidence-card'
import { IdeaBoard } from '@/components/idea-board'
import { PanelBoundary } from '@/components/panel-boundary'
import { DiscoveryError, useDiscovery } from '@/hooks/use-discovery'
import { cn } from '@/lib/utils'
import { useSessionStore } from '@/stores/session'
import { useSettings } from '@/stores/settings'

interface WorkpaneProps {
  className?: string
}

/**
 * Markdown from Cala, rendered with react-markdown's default element set.
 *
 * Raw HTML is off — no `rehype-raw`, no `dangerouslySetInnerHTML`. That default *is* the
 * sanitisation: the answer is text from a source we do not control, and the only safe way to
 * show it is to let the parser decide what an element is.
 */
const MARKDOWN_COMPONENTS: Components = {
  p: ({ children }) => (
    <p className="text-[15px] text-neutral-700 leading-[1.75] dark:text-neutral-300">{children}</p>
  ),
  strong: ({ children }) => (
    <strong className="font-medium text-neutral-900 dark:text-neutral-100">{children}</strong>
  ),
  h1: ({ children }) => (
    <h3 className="pt-2 font-medium text-base text-neutral-900 dark:text-neutral-100">
      {children}
    </h3>
  ),
  h2: ({ children }) => (
    <h3 className="pt-2 font-medium text-base text-neutral-900 dark:text-neutral-100">
      {children}
    </h3>
  ),
  h3: ({ children }) => (
    <h4 className="pt-1 font-medium text-[15px] text-neutral-900 dark:text-neutral-100">
      {children}
    </h4>
  ),
  ul: ({ children }) => (
    <ul className="flex list-disc flex-col gap-1.5 pl-5 marker:text-neutral-300 dark:marker:text-neutral-600">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="flex list-decimal flex-col gap-1.5 pl-5 marker:text-neutral-400 dark:marker:text-neutral-500">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="text-[15px] text-neutral-700 leading-[1.7] dark:text-neutral-300">{children}</li>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="underline decoration-neutral-300 underline-offset-2 dark:decoration-neutral-600"
    >
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-neutral-100 px-1 py-0.5 text-[13px] dark:bg-neutral-800">
      {children}
    </code>
  ),
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="max-w-[52ch] text-neutral-500 text-sm dark:text-neutral-400">{children}</p>
}

/** A quiet skeleton. No spinner — a spinner asks to be watched, and this takes a moment. */
function Skeleton() {
  return (
    <div aria-hidden className="flex animate-pulse flex-col gap-6">
      <div className="flex flex-col gap-2">
        <div className="h-4 w-40 rounded bg-neutral-200 dark:bg-neutral-800" />
        <div className="h-3 w-64 rounded bg-neutral-100 dark:bg-neutral-900" />
      </div>
      <div className="flex flex-col gap-2">
        <div className="h-3 w-full max-w-[38rem] rounded bg-neutral-100 dark:bg-neutral-900" />
        <div className="h-3 w-full max-w-[34rem] rounded bg-neutral-100 dark:bg-neutral-900" />
        <div className="h-3 w-full max-w-[22rem] rounded bg-neutral-100 dark:bg-neutral-900" />
      </div>
    </div>
  )
}

function ResolvedEntityHeader({ entity }: { entity: ResolvedEntity }) {
  return (
    <header
      style={{ '--discovery-index': 0 } as CSSProperties}
      className="discovery-item flex max-w-[65ch] flex-col gap-2"
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <h2 className="font-medium text-lg text-neutral-900 tracking-tight dark:text-neutral-50">
          {entity.name}
        </h2>
        {entity.entity_type ? (
          <span className="rounded-full border border-neutral-200 px-2 py-0.5 text-[11px] text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
            {entity.entity_type}
          </span>
        ) : null}
      </div>
      {entity.description ? (
        <p className="text-[15px] text-neutral-600 leading-relaxed dark:text-neutral-400">
          {entity.description}
        </p>
      ) : null}
    </header>
  )
}

function Result({ data }: { data: DiscoverResponse }) {
  if (data.status === 'rate_limited' || data.status === 'budget_exhausted') {
    return (
      <div className="discovery-item">
        <Note>
          {data.status === 'rate_limited'
            ? 'Source lookup is rate limited right now. The transcript keeps running.'
            : `The source-lookup budget is spent (${data.ledger.spent} of ${data.ledger.budget} credits). No further queries will be made.`}
        </Note>
      </div>
    )
  }

  // Cala's coverage is finance, legal and health; most spoken subjects miss it. Saying so is
  // the honest answer — an unsourced model answer must never be dressed up as a grounded one.
  if (data.status === 'empty' || !data.answer) {
    return (
      <div className="flex flex-col gap-2">
        {data.entity ? <ResolvedEntityHeader entity={data.entity} /> : null}
        <Note>No cited sources for this yet.</Note>
      </div>
    )
  }

  return (
    <>
      {data.entity ? <ResolvedEntityHeader entity={data.entity} /> : null}

      <div
        style={{ '--discovery-index': 1 } as CSSProperties}
        className="discovery-item flex max-w-[65ch] flex-col gap-4"
      >
        <Markdown components={MARKDOWN_COMPONENTS}>{data.answer}</Markdown>
      </div>

      {data.context.length > 0 ? (
        <section aria-label="Evidence" className="flex flex-col gap-6">
          <h3 className="font-medium text-[11px] text-neutral-400 uppercase tracking-[0.1em] dark:text-neutral-500">
            Evidence
          </h3>
          {data.context.map((item, index) => (
            <EvidenceCard key={item.id} item={item} index={index} />
          ))}
        </section>
      ) : null}
    </>
  )
}

/**
 * The Cala half of the pane: entity, answer, evidence. Secondary by construction.
 *
 * Every branch returns something small. Nothing in here is allowed to be the reason the
 * pane is empty — the grid above it arrives over the WebSocket and owes this nothing.
 */
function CalaPanel() {
  const { data, isFetching, error } = useDiscovery()
  const loading = isFetching && !data
  const correlationId = error instanceof DiscoveryError ? error.correlationId : null

  if (loading) {
    return (
      <div className="discovery-item">
        <Skeleton />
      </div>
    )
  }
  if (error) {
    return (
      <div className="discovery-item">
        <Note>Source lookup failed. Reference {correlationId ?? 'unknown'}.</Note>
      </div>
    )
  }
  if (!data) {
    return null
  }
  return (
    // Keyed on the query so a new settled turn remounts the subtree and replays the entry.
    <div key={`${data.session_id}:${data.query}`} className="flex flex-col gap-8">
      <Result data={data} />
    </div>
  )
}

/**
 * The right two thirds of the working layout.
 *
 * The grid is the primary content. It arrives over the WebSocket in waves from the two
 * open-corpus lanes, and it is the thing the user asked for by speaking. Cala's entity,
 * answer and evidence sit underneath it as supporting material: useful when it lands,
 * never load-bearing. That ordering is also the failure model — Cala going slow, erroring,
 * or being unreachable entirely leaves the grid untouched, and a throw while rendering it
 * is caught by the boundary rather than blanking the pane.
 *
 * The `IdeaBoard` placeholder still holds the space, but only while nothing real exists at
 * all: no images, nothing in flight, nothing answered. The moment either half has something
 * to show, the demo stickers step aside so they are never mistaken for sourced content.
 */
export function Workpane({ className }: WorkpaneProps) {
  const output = useSettings((state) => state.output)
  const candidateCount = useSessionStore((state) => state.candidates.length)
  const { data, isFetching, error } = useDiscovery()

  const showGrid = output === 'images' || output === 'both'
  const showCala = output === 'text' || output === 'both'
  const hasGrid = showGrid && candidateCount > 0
  const calaHasSomething = showCala && (isFetching || Boolean(data) || Boolean(error))

  // Nothing found, nothing asked, nothing failed: the gate has not opened yet.
  if (!hasGrid && !calaHasSomething) {
    return <IdeaBoard className={className} />
  }

  return (
    <section
      aria-label="Workpane"
      aria-busy={showCala && isFetching && !data}
      className={cn('flex min-h-0 flex-col gap-8 overflow-y-auto p-5 md:p-8', className)}
    >
      {/*
        Entry only, no exit. `main` dropped the `motion` dependency when the session screen
        went CSS-only, so tiles animate through `.candidate-tile` and the Cala items through
        `.discovery-item` in index.css, on the same curve as `workspace-enter` and
        `sticker-enter`, and both honour the existing reduced-motion opt-out.
      */}
      {hasGrid ? <CandidateGrid /> : null}
      {showCala ? (
        <PanelBoundary
          fallback={
            <div className="discovery-item">
              <Note>Sources could not be displayed.</Note>
            </div>
          }
        >
          <CalaPanel />
        </PanelBoundary>
      ) : null}
    </section>
  )
}
