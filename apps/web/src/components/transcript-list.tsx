import { VOICE_COMMAND_KEYWORDS } from '@/lib/voice-commands'
import { useSessionStore } from '@/stores/session'

const KEYWORD_STOPWORDS = new Set([
  'aquest',
  'aquesta',
  'avec',
  'con',
  'des',
  'els',
  'estoy',
  'faire',
  'las',
  'los',
  'mais',
  'more',
  'pour',
  'que',
  'quiero',
  'sobre',
  'the',
  'una',
  'unas',
  'une',
  'uns',
  'want',
  'with',
  'vull',
])

function formatTranscriptText(text: string): string {
  return text
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/\s+([,.;!?])/g, '$1')
    .replace(/([,;!?])(?=\S)/g, '$1 ')
}

function tokenKey(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^\p{L}\p{N}]/gu, '')
    .toLocaleLowerCase()
}

export function transcriptKeywordTokens(keywordPhrases: readonly string[]): Set<string> {
  return new Set(
    keywordPhrases
      .flatMap((phrase) => phrase.split(/\s+/))
      .map(tokenKey)
      .filter((token) => token.length > 2 && !KEYWORD_STOPWORDS.has(token)),
  )
}

/**
 * The rolling transcript, in the chat column above the microphone.
 *
 * Speech scaffolding stays grey. Words used by the current Fastino/OpenAI direction turn black,
 * so the transcript makes the inputs driving the visual field explicit.
 */
export function TranscriptList() {
  const transcript = useSessionStore((state) => state.transcript)
  const transcriptSegments = useSessionStore((state) => state.transcriptSegments)
  const intent = useSessionStore((state) => state.intent)
  const ideasUpdate = useSessionStore((state) => state.ideasUpdate)
  const connectionState = useSessionStore((state) => state.connectionState)
  const connectionError = useSessionStore((state) => state.connectionError)
  const transcriptLines =
    transcriptSegments.length > 0
      ? transcriptSegments
      : transcript.trim()
        ? [{ itemId: 'transcript-fallback', text: transcript, complete: false }]
        : []
  const keywordPhrases =
    ideasUpdate?.keywords ??
    (intent
      ? [
          intent.subject,
          ...intent.moods,
          ...intent.styles,
          ...intent.palette,
          intent.composition,
          intent.medium,
          intent.era,
        ]
      : [])
  const keywordTokens = transcriptKeywordTokens([...keywordPhrases, ...VOICE_COMMAND_KEYWORDS])

  return (
    <section aria-live="polite" aria-label="Live transcript" className="pb-4">
      {transcriptLines.length > 0 ? (
        <div className="transcript-copy text-[clamp(1.7rem,3vw,3rem)] font-medium leading-[1.04] tracking-[-0.052em]">
          {transcriptLines.map((segment) => {
            const words = [...formatTranscriptText(segment.text).matchAll(/\S+\s*/g)]

            return (
              <p className="transcript-line" key={segment.itemId}>
                {words.map((word) => {
                  const isKeyword = keywordTokens.has(tokenKey(word[0]))
                  return (
                    <span
                      className={`transcript-word ${isKeyword ? 'font-semibold text-neutral-950' : 'text-neutral-400'}`}
                      key={`${segment.itemId}-${word.index}`}
                    >
                      {word[0]}
                    </span>
                  )
                })}
              </p>
            )
          })}
        </div>
      ) : connectionState === 'error' ? (
        <p role="alert" className="max-w-md text-lg font-medium leading-snug text-red-700">
          {connectionError ?? 'Live transcription could not start.'}
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
