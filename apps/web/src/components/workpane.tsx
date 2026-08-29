import type { DiscoverResponse, ResolvedEntity } from '@glia/api-client'
import type { CSSProperties } from 'react'
import Markdown, { type Components } from 'react-markdown'
import { EvidenceCard } from '@/components/evidence-card'
import { GeneratedImage } from '@/components/generated-image'
import { IdeaBoard } from '@/components/idea-board'
import { DiscoveryError, useDiscovery } from '@/hooks/use-discovery'
import { cn } from '@/lib/utils'
import { useSessionStore } from '@/stores/session'

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
 * The right two thirds of the working layout.
 *
 * Two things want this space and only one of them is real yet. Until the distiller gate opens
 * and Cala answers, the placeholder `IdeaBoard` holds it — clearly badged `demo`, because
 * nothing on it is sourced. The moment a lookup is in flight or has landed, the pane belongs to
 * what Cala actually cited: sourced content outranks a placeholder, and the two must never be
 * on screen together or the demo stickers read as evidence.
 *
 * A generated image takes precedence over both. It is the last beat of the session and the only
 * place the prompt that produced it can be read, so it holds the pane until the next one lands.
 *
 * Every state below is a real outcome. None is a crash, and none invents an answer Cala did
 * not cite.
 */
export function Workpane({ className }: WorkpaneProps) {
  const { data, isFetching, error } = useDiscovery()
  const generated = useSessionStore((state) => state.generation)

  // A generated image outranks everything: it is the thing the user just asked for, and it is
  // the only surface where the prompt that produced it can be read. Nothing replaces it until
  // the next Generate lands — a failure keeps its line in the rail rather than taking this pane.
  if (generated) {
    return (
      <section
        aria-label="Generated image"
        className={cn('flex min-h-0 flex-col overflow-y-auto p-5 md:p-8', className)}
      >
        <GeneratedImage value={generated} />
      </section>
    )
  }

  const loading = isFetching && !data
  const correlationId = error instanceof DiscoveryError ? error.correlationId : null

  // Nothing asked, nothing answered, nothing failed: the gate has not opened yet.
  if (!loading && !error && !data) {
    return <IdeaBoard className={className} />
  }

  return (
    <section
      aria-label="Workpane"
      aria-busy={loading}
      className={cn('min-h-0 overflow-y-auto p-5 md:p-8', className)}
    >
      {/*
        Entry only, no exit. `main` dropped the `motion` dependency when the session screen went
        CSS-only, so these animate through `.discovery-item` in index.css on the same curve as
        `workspace-enter` and `sticker-enter`, and honour the existing reduced-motion opt-out.
      */}
      {loading ? (
        <div className="discovery-item">
          <Skeleton />
        </div>
      ) : error ? (
        <div className="discovery-item">
          <Note>Source lookup failed. Reference {correlationId ?? 'unknown'}.</Note>
        </div>
      ) : data ? (
        // Keyed on the query so a new settled turn remounts the subtree and replays the entry.
        <div key={`${data.session_id}:${data.query}`} className="flex flex-col gap-8">
          <Result data={data} />
        </div>
      ) : null}
    </section>
  )
}
