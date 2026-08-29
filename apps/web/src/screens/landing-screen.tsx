import { Mic } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useMicrophone } from '@/hooks/use-microphone'
import { useRealtimeTranscription } from '@/hooks/use-realtime-transcription'
import { cn } from '@/lib/utils'
import { type MicState, useSessionStore } from '@/stores/session'

const CAPTIONS: Record<MicState, string> = {
  idle: 'Speak your mind.',
  requesting: 'Speak your mind.',
  granted: 'Listening.',
  denied: 'Microphone access denied.',
  unsupported: 'Microphone unavailable.',
}

export function LandingScreen() {
  const { micState, toggle } = useMicrophone()
  useRealtimeTranscription()
  const connectionState = useSessionStore((state) => state.connectionState)
  const transcript = useSessionStore((state) => state.transcript)
  const intent = useSessionStore((state) => state.intent)
  const isListening = micState === 'granted'
  const caption =
    connectionState === 'connecting'
      ? 'Connecting.'
      : connectionState === 'error'
        ? 'Connection interrupted.'
        : CAPTIONS[micState]

  return (
    <main className="flex min-h-dvh items-center justify-center bg-white dark:bg-neutral-950">
      <Button
        type="button"
        variant="outline"
        onClick={toggle}
        aria-pressed={isListening}
        className={cn(
          // The whole card is the control. Only the border reacts; nothing moves.
          'h-auto w-auto flex-col gap-5 rounded-2xl px-20 py-16 shadow-none transition-colors',
          'active:not-aria-[haspopup]:translate-y-0',
          'border-neutral-200 bg-transparent hover:border-neutral-300 hover:bg-transparent',
          'dark:border-neutral-800 dark:bg-transparent',
          'dark:hover:border-neutral-700 dark:hover:bg-transparent',
          micState === 'denied' &&
            'border-red-200 hover:border-red-300 dark:border-red-900/70 dark:hover:border-red-900',
        )}
      >
        <span
          className={cn(
            'flex size-16 items-center justify-center rounded-full transition-colors',
            isListening && 'bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900',
          )}
        >
          <Mic className={cn('size-7', micState === 'requesting' && 'animate-pulse opacity-50')} />
        </span>
        <span className="font-normal text-neutral-500 text-sm dark:text-neutral-400">
          {caption}
        </span>
      </Button>
      {transcript ? (
        <section
          aria-live="polite"
          aria-label="Live transcript"
          className="fixed inset-x-6 bottom-8 max-w-2xl text-left sm:left-10 sm:right-auto"
        >
          <p className="font-medium text-base text-neutral-900 leading-relaxed dark:text-neutral-100">
            {transcript}
          </p>
          {intent?.subject ? (
            <p className="mt-1 text-neutral-400 text-sm dark:text-neutral-600">{intent.subject}</p>
          ) : null}
        </section>
      ) : null}
    </main>
  )
}
