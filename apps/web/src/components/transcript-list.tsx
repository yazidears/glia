import { useSessionStore } from '@/stores/session'

/**
 * The rolling transcript, in the chat column above the microphone.
 *
 * Renders nothing at all until there are words — no placeholder copy, no skeleton. The text comes
 * from the transcription provider, so it is rendered as text and never as markup.
 */
export function TranscriptList() {
  const transcript = useSessionStore((state) => state.transcript)
  const intent = useSessionStore((state) => state.intent)

  if (!transcript) {
    return null
  }

  return (
    <section aria-live="polite" aria-label="Live transcript" className="flex flex-col gap-1 pb-4">
      <p className="font-medium text-base text-neutral-900 leading-relaxed dark:text-neutral-100">
        {transcript}
      </p>
      {intent?.subject ? (
        <p className="text-neutral-500 text-sm dark:text-neutral-500">{intent.subject}</p>
      ) : null}
    </section>
  )
}
