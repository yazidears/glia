import type { Candidate, VisualIntent } from '@glia/api-client'
import { X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { type GeneratedImage, type PinnedRef, useSessionStore } from '@/stores/session'

/**
 * The whole session on one page: the image, the prompt that produced it, the attributes the
 * distiller pulled out, what Cala cited, the pins, and — last and folded away — the speech.
 *
 * This is a render, not a feature. Every value on this page is already in the browser: the
 * transcript and pins in the store, the intent from the distiller, and the Cala evidence already
 * carried by cited WebSocket candidates. So it opens instantly, costs no request and spends no
 * Cala credit, and it cannot fail in a way that takes the session with it.
 *
 * The order is deliberate and it is not the order the session happened in. Spoken thinking is
 * rambling — it is the raw material, not the result — so the finished thing leads and the
 * speech is a `<details>` at the bottom for anyone who wants to check the work. What sits in
 * between is the part that is hard to get anywhere else: a distilled brief with sources you can
 * click.
 *
 * The transcript never leaves the browser to get here. `synthesis.py` sends fal a summary and
 * never the speech; this page reads the same text straight out of the store. What the user said
 * is on their screen and nowhere else, which is a property worth keeping rather than a detail.
 */

const ATTRIBUTE_LABELS: ReadonlyArray<readonly [keyof VisualIntent, string]> = [
  ['subject', 'Subject'],
  ['moods', 'Mood'],
  ['styles', 'Style'],
  ['palette', 'Palette'],
  ['composition', 'Composition'],
  ['medium', 'Medium'],
  ['era', 'Era'],
]

interface Attribute {
  label: string
  value: string
}

/** The distilled intent as label/value pairs, with the empty fields dropped rather than blanked. */
function attributesOf(intent: VisualIntent | null): Attribute[] {
  if (!intent) {
    return []
  }
  const rows: Attribute[] = []
  for (const [key, label] of ATTRIBUTE_LABELS) {
    const raw = intent[key]
    const value = Array.isArray(raw) ? raw.join(', ') : (raw ?? '')
    if (value.trim()) {
      rows.push({ label, value })
    }
  }
  return rows
}

/**
 * Every distinct document behind an answer, in citation order.
 *
 * Deduped by identity rather than position, exactly as `EvidenceCard` does it: Cala returns the
 * same document under several context items, and a bibliography that lists one source four
 * times is worse than useless in something a person is going to send to a client.
 */
interface Citation {
  url: string
  title: string
  publisher: string | null
}

function citationsOf(candidates: readonly Candidate[]): Citation[] {
  const seen = new Map<string, Citation>()
  for (const candidate of candidates) {
    if (candidate.lane !== 'cited' || seen.has(candidate.source_url)) {
      continue
    }
    seen.set(candidate.source_url, {
      url: candidate.source_url,
      title: candidate.title ?? candidate.entity_name ?? 'Untitled source',
      publisher: candidate.publisher,
    })
  }
  return [...seen.values()]
}

function researchOf(candidates: readonly Candidate[]): string[] {
  return [
    ...new Set(
      candidates
        .filter((candidate) => candidate.lane === 'cited' && candidate.evidence)
        .map((candidate) => candidate.evidence?.trim() ?? '')
        .filter(Boolean),
    ),
  ]
}

/** The report as plain text, for pasting into a brief. Mirrors the page, minus the images. */
function asPlainText(
  generated: GeneratedImage,
  attributes: Attribute[],
  research: string[],
  citations: Citation[],
  pinned: PinnedRef[],
  transcript: string,
): string {
  const dropped = new Set(generated.unavailableReferences)
  const blocks: string[] = ['GLIA SESSION REPORT', '', 'PROMPT', generated.prompt]
  blocks.push('', `${generated.model} · ${generated.referenceCount} reference images`)
  blocks.push('', 'IMAGE', generated.imageUrl)
  if (attributes.length > 0) {
    blocks.push('', 'THE IDEA')
    blocks.push(...attributes.map(({ label, value }) => `${label}: ${value}`))
  }
  if (research.length > 0) {
    blocks.push('', 'RESEARCH', ...research)
  }
  if (citations.length > 0) {
    blocks.push('', 'SOURCES')
    blocks.push(
      ...citations.map((citation) => {
        return [
          citation.publisher ? `${citation.title} — ${citation.publisher}` : citation.title,
          citation.url,
        ]
          .filter(Boolean)
          .join(' · ')
      }),
    )
  }
  if (pinned.length > 0) {
    blocks.push('', 'PINNED REFERENCES')
    blocks.push(
      ...pinned.map((pin) =>
        [pin.title, pin.sourceUrl, dropped.has(pin.id) ? '(not used for conditioning)' : '']
          .filter(Boolean)
          .join(' · '),
      ),
    )
  }
  blocks.push('', 'WHAT YOU SAID', transcript.trim())
  return blocks.join('\n')
}

type CopyState = 'idle' | 'copied' | 'failed'

interface ReportBodyProps {
  generated: GeneratedImage
  onClose: () => void
}

function ReportBody({ generated, onClose }: ReportBodyProps) {
  const transcript = useSessionStore((state) => state.transcript)
  const intent = useSessionStore((state) => state.intent)
  const pinned = useSessionStore((state) => state.pinned)
  const candidates = useSessionStore((state) => state.candidates)
  const [copied, setCopied] = useState<CopyState>('idle')
  const transcriptRef = useRef<HTMLDetailsElement>(null)

  // Fixed at open. A timestamp that ticked while the page was on screen would be describing the
  // reading, not the session.
  const exportedAt = useMemo(() => new Date(), [])
  const attributes = useMemo(() => attributesOf(intent), [intent])
  const citations = useMemo(() => citationsOf(candidates), [candidates])
  const research = useMemo(() => researchOf(candidates), [candidates])
  const dropped = useMemo(
    () => new Set(generated.unavailableReferences),
    [generated.unavailableReferences],
  )

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // A closed `<details>` prints as its summary line, and CSS cannot reliably reopen it — the
  // content is slotted and browsers disagree about whether a print rule reaches it. So the
  // element is opened before the page is painted, which also covers the user's own Cmd-P.
  useEffect(() => {
    function open() {
      if (transcriptRef.current) {
        transcriptRef.current.open = true
      }
    }
    window.addEventListener('beforeprint', open)
    return () => window.removeEventListener('beforeprint', open)
  }, [])

  function printReport() {
    if (transcriptRef.current) {
      transcriptRef.current.open = true
    }
    window.print()
  }

  async function copy() {
    const text = asPlainText(generated, attributes, research, citations, pinned, transcript)
    try {
      await navigator.clipboard.writeText(text)
      setCopied('copied')
    } catch {
      // Clipboard access is denied outside a secure context and in some embedded views. Saying
      // so is the honest outcome; the page is still readable and still printable.
      setCopied('failed')
    }
    window.setTimeout(() => setCopied('idle'), 2400)
  }

  return (
    <div className="report-sheet" role="dialog" aria-modal="true" aria-label="Session report">
      <div className="report-actions">
        <button type="button" className="report-action" onClick={copy}>
          {copied === 'copied' ? 'Copied' : copied === 'failed' ? 'Copy blocked' : 'Copy as text'}
        </button>
        <button type="button" className="report-action" onClick={printReport}>
          Print
        </button>
        <button type="button" className="report-close" aria-label="Close report" onClick={onClose}>
          <X aria-hidden="true" strokeWidth={2.2} />
        </button>
      </div>

      <article className="report">
        <header className="report-header">
          <p className="report-eyebrow">Session report</p>
          <h1 className="report-title">{intent?.subject || 'Untitled session'}</h1>
          <p className="report-dateline">
            {exportedAt.toLocaleDateString(undefined, {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </p>
        </header>

        <section className="report-section report-section--image">
          <img alt={generated.prompt} className="report-image" src={generated.imageUrl} />
          <p className="report-prompt">{generated.prompt}</p>
          <p className="report-meta">
            {generated.model} · {generated.referenceCount}{' '}
            {generated.referenceCount === 1 ? 'reference image' : 'reference images'}
          </p>
        </section>

        {attributes.length > 0 ? (
          <section className="report-section">
            <h2 className="report-heading">The idea</h2>
            <dl className="report-attributes">
              {attributes.map(({ label, value }) => (
                <div className="report-attribute" key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}

        {research.length > 0 ? (
          <section className="report-section">
            <h2 className="report-heading">Research</h2>
            <div className="report-prose">
              {research.map((note) => (
                <p key={note}>{note}</p>
              ))}
            </div>
          </section>
        ) : null}

        {citations.length > 0 ? (
          <section className="report-section">
            <h2 className="report-heading">Sources</h2>
            <ol className="report-citations">
              {citations.map((citation) => {
                return (
                  <li key={citation.url}>
                    <a href={citation.url} target="_blank" rel="noreferrer noopener">
                      {citation.title}
                    </a>
                    {citation.publisher ? (
                      <span className="report-publisher">{citation.publisher}</span>
                    ) : null}
                    {/* Printed pages have no links, so the URL is set as text beside the name. */}
                    <span className="report-url">{citation.url}</span>
                  </li>
                )
              })}
            </ol>
          </section>
        ) : null}

        {pinned.length > 0 ? (
          <section className="report-section">
            <h2 className="report-heading">
              Pinned references
              <span className="report-heading-note">conditioning input</span>
            </h2>
            <ul className="report-pins">
              {pinned.map((pin) => (
                <li className="report-pin" key={pin.id}>
                  {pin.imageUrl ? (
                    <img alt="" className="report-pin-image" src={pin.imageUrl} />
                  ) : (
                    // No URL means no thumbnail, and none is invented. The title is what
                    // actually reached the prompt, so the title is what the tile shows.
                    <span className="report-pin-placeholder">{pin.title}</span>
                  )}
                  <span className="report-pin-caption">
                    {pin.sourceUrl ? (
                      <a href={pin.sourceUrl} target="_blank" rel="noreferrer noopener">
                        {pin.title}
                      </a>
                    ) : (
                      pin.title
                    )}
                    {/*
                      Carried through from the generation rather than recomputed. A pin the
                      server could not fetch steered the words and not the pixels, and a report
                      that showed it as a reference image would be overstating what happened.
                    */}
                    {dropped.has(pin.id) ? (
                      <span className="report-pin-dropped">not used for conditioning</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className="report-section">
          <details className="report-transcript" ref={transcriptRef}>
            <summary>What you said</summary>
            <p>{transcript.trim()}</p>
          </details>
        </section>

        <footer className="report-footer">
          Distilled by Pioneer · researched with Cala · generated with fal · made with Glia
        </footer>
      </article>
    </div>
  )
}

interface SessionReportProps {
  generated: GeneratedImage
}

/**
 * The button, and the overlay it opens.
 *
 * Both live here so nothing above has to hold state for a panel it does not render. The overlay
 * is portalled to `body` because it must escape the workpane's `overflow-y-auto`, and because
 * the print stylesheet needs it as a sibling of the app rather than a descendant.
 */
export function SessionReport({ generated }: SessionReportProps) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button type="button" className="report-open" onClick={() => setOpen(true)}>
        Session report
      </button>
      {open
        ? createPortal(
            <ReportBody generated={generated} onClose={() => setOpen(false)} />,
            document.body,
          )
        : null}
    </>
  )
}
