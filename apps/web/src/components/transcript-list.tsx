import { useSessionStore } from '@/stores/session'

/**
 * The rolling transcript, in the chat column above the microphone.
 *
 * Interim words stay grey. A completed turn — or the words that caused a new reference batch —
 * settles to black, so the transcript and the visual field feel causally connected.
 */
export function TranscriptList() {
  const transcript = useSessionStore((state) => state.transcript)
  const transcriptSegments = useSessionStore((state) => state.transcriptSegments)
  const processedWordCount = useSessionStore((state) => state.processedWordCount)
  const transcriptWords = [...transcript.matchAll(/\S+\s*/g)].map((match) => ({
    text: match[0],
    offset: match.index,
  }))
  const completedWordCount = transcriptSegments
    .filter((segment) => segment.complete)
    .reduce((count, segment) => count + (segment.text.match(/\S+/g)?.length ?? 0), 0)
  const blackWordCount = Math.max(processedWordCount, completedWordCount)

  return (
    <section aria-live="polite" aria-label="Live transcript" className="pb-4">
      {transcriptWords.length > 0 ? (
        <p className="text-[clamp(1.7rem,3vw,3rem)] font-medium leading-[1.04] tracking-[-0.052em]">
          {transcriptWords.map((word, index) => (
            <span
              className={index < blackWordCount ? 'text-neutral-950' : 'text-neutral-500'}
              key={word.offset}
            >
              {word.text}
            </span>
          ))}
        </p>
      ) : (
        <p className="flex items-baseline gap-2 text-2xl font-medium tracking-[-0.04em] text-neutral-500">
          Speak now.
          <span aria-hidden="true" className="listening-dots">
            <span />
            <span />
            <span />
          </span>
        </p>
      )}
    </section>
  )
}
