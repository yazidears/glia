import type { DiscoverResponse, ResolvedEntity } from '@glia/api-client'
import { motion, type Transition, useReducedMotion, type Variants } from 'motion/react'
import Markdown, { type Components } from 'react-markdown'
import { EvidenceCard } from '@/components/evidence-card'
import { DiscoveryError, useDiscovery } from '@/hooks/use-discovery'
import { cn, INSTANT, SPRING } from '@/lib/utils'

interface WorkpaneProps {
  className?: string
}

/**
 * Sections arrive as a wave rather than a flash — entity, then answer, then evidence.
 *
 * `shown` carries a real property and not only a `transition`. A variant with nothing to
 * animate gives Motion no target, the label stops propagating, and the children sit at
 * `hidden` forever — which renders as an empty workpane holding a perfectly good answer.
 */
const CONTAINER: Variants = {
  hidden: { opacity: 0 },
  shown: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.04 } },
}

const ITEM: Variants = {
  hidden: { opacity: 0, y: 10 },
  shown: { opacity: 1, y: 0 },
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
    <motion.header variants={ITEM} className="flex max-w-[65ch] flex-col gap-2">
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
    </motion.header>
  )
}

function Result({ data, transition }: { data: DiscoverResponse; transition: Transition }) {
  if (data.status === 'rate_limited' || data.status === 'budget_exhausted') {
    return (
      <motion.div variants={ITEM}>
        <Note>
          {data.status === 'rate_limited'
            ? 'Source lookup is rate limited right now. The transcript keeps running.'
            : `The source-lookup budget is spent (${data.ledger.spent} of ${data.ledger.budget} credits). No further queries will be made.`}
        </Note>
      </motion.div>
    )
  }

  // Cala's coverage is finance, legal and health; most spoken subjects miss it. Saying so is
  // the honest answer — an unsourced model answer must never be dressed up as a grounded one.
  if (data.status === 'empty' || !data.answer) {
    return (
      <motion.div variants={ITEM} className="flex flex-col gap-2">
        {data.entity ? <ResolvedEntityHeader entity={data.entity} /> : null}
        <Note>No cited sources for this yet.</Note>
      </motion.div>
    )
  }

  return (
    <>
      {data.entity ? <ResolvedEntityHeader entity={data.entity} /> : null}

      <motion.div variants={ITEM} className="flex max-w-[65ch] flex-col gap-4">
        <Markdown components={MARKDOWN_COMPONENTS}>{data.answer}</Markdown>
      </motion.div>

      {data.context.length > 0 ? (
        <motion.section variants={ITEM} aria-label="Evidence" className="flex flex-col gap-6">
          <h3 className="font-medium text-[11px] text-neutral-400 uppercase tracking-[0.1em] dark:text-neutral-500">
            Evidence
          </h3>
          {data.context.map((item) => (
            <EvidenceCard key={item.id} item={item} transition={transition} />
          ))}
        </motion.section>
      ) : null}
    </>
  )
}

/**
 * The right two thirds of the working layout: what Cala found for the current settled turn.
 *
 * Stays empty until there is something true to show. Every state below is a real outcome —
 * none of them is a crash, and none of them invents an answer Cala did not cite.
 */
export function Workpane({ className }: WorkpaneProps) {
  const { data, isFetching, error } = useDiscovery()
  const prefersReducedMotion = useReducedMotion() === true
  const transition = prefersReducedMotion ? INSTANT : SPRING

  const loading = isFetching && !data
  const correlationId = error instanceof DiscoveryError ? error.correlationId : null

  return (
    <section
      aria-label="Workpane"
      aria-busy={loading}
      className={cn('min-h-0 overflow-y-auto p-5 md:p-8', className)}
    >
      {/*
        No `AnimatePresence`: these states swap once per settled turn and nothing here needs to
        animate on the way out. Only the entry is animated, and the `key` is what replays it
        when a new turn arrives.
      */}
      {loading ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={transition}>
          <Skeleton />
        </motion.div>
      ) : error ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={transition}>
          <Note>Source lookup failed. Reference {correlationId ?? 'unknown'}.</Note>
        </motion.div>
      ) : data ? (
        <motion.div
          key={`${data.session_id}:${data.query}`}
          variants={CONTAINER}
          initial="hidden"
          animate="shown"
          className="flex flex-col gap-8"
        >
          <Result data={data} transition={transition} />
        </motion.div>
      ) : null}
    </section>
  )
}
