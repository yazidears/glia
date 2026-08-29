import { Mic } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Waveform } from '@/components/waveform'
import { useAudioLevel } from '@/hooks/use-audio-level'
import { useMicrophone } from '@/hooks/use-microphone'
import { cn } from '@/lib/utils'
import type { MicState } from '@/stores/session'

const CAPTIONS: Record<MicState, string> = {
  idle: 'Speak your mind.',
  requesting: 'Speak your mind.',
  granted: 'Listening.',
  denied: 'Microphone access denied.',
  unsupported: 'Microphone unavailable.',
}

export function LandingScreen() {
  const { micState, toggle } = useMicrophone()
  const audio = useAudioLevel()
  const isListening = micState === 'granted'

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
        <Waveform handle={audio} variant="hero" />
        <span className="font-normal text-neutral-500 text-sm dark:text-neutral-400">
          {CAPTIONS[micState]}
        </span>
      </Button>
    </main>
  )
}
