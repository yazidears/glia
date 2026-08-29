import type { ConnectionState } from '@glia/api-client'
import { Mic } from 'lucide-react'
import {
  AnimatePresence,
  LayoutGroup,
  motion,
  type Transition,
  useReducedMotion,
} from 'motion/react'
import { TranscriptList } from '@/components/transcript-list'
import { Waveform } from '@/components/waveform'
import { Workpane } from '@/components/workpane'
import { type AudioLevelHandle, useAudioLevel } from '@/hooks/use-audio-level'
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

/**
 * Once permission is settled, what the user is waiting on is the transcription link rather than
 * the device, so the connection outranks the microphone in the caption.
 */
function captionFor(micState: MicState, connectionState: ConnectionState): string {
  if (connectionState === 'connecting') {
    return 'Connecting.'
  }
  if (connectionState === 'error') {
    return 'Connection interrupted.'
  }
  return CAPTIONS[micState]
}

/** One shared identity, so the hero card and the docked mic are the same element travelling. */
const MIC_LAYOUT_ID = 'glia-mic'

/** Roughly half a second of settle. A spring, because the card has weight and a duration reads flat. */
const SPRING: Transition = { type: 'spring', stiffness: 240, damping: 28, mass: 0.9 }
const INSTANT: Transition = { duration: 0 }

interface MicControlProps {
  variant: 'hero' | 'dock'
  micState: MicState
  audio: AudioLevelHandle
  transition: Transition
  onToggle: () => void
}

/**
 * The microphone, in both of the places it lives. It is one component and one `layoutId`, so
 * moving between them is a shared-element transition rather than a fade out followed by a fade in.
 */
function MicControl({ variant, micState, audio, transition, onToggle }: MicControlProps) {
  const isHero = variant === 'hero'
  const isListening = micState === 'granted'

  return (
    <motion.button
      type="button"
      layoutId={MIC_LAYOUT_ID}
      layout
      transition={transition}
      onClick={onToggle}
      aria-pressed={isListening}
      aria-label={isListening ? 'Stop listening' : 'Start listening'}
      className={cn(
        'pointer-events-auto relative flex items-center justify-center rounded-2xl outline-none',
        'focus-visible:ring-3 focus-visible:ring-ring/50',
        isHero ? 'flex-col gap-6 px-20 py-14' : 'w-full flex-row justify-start gap-3 px-3 py-2',
      )}
    >
      {/*
       * The card's border is its own layer so it can fade out over the travel. A border set by a
       * class would simply not be there on the docked instance, which pops instead of animating.
       */}
      <motion.span
        aria-hidden
        layout
        initial={{ opacity: 1 }}
        animate={{ opacity: isHero ? 1 : 0 }}
        transition={transition}
        style={{ borderRadius: 16 }}
        className={cn(
          'pointer-events-none absolute inset-0 border',
          micState === 'denied' ? 'border-destructive/40' : 'border-border',
        )}
      />
      <motion.span
        layout
        transition={transition}
        className={cn(
          'flex shrink-0 items-center justify-center rounded-full transition-colors',
          isHero ? 'size-16' : 'size-9',
          isListening && 'bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900',
        )}
      >
        <Mic
          className={cn(
            isHero ? 'size-7' : 'size-4',
            micState === 'requesting' && 'animate-pulse opacity-50',
          )}
        />
      </motion.span>
      <motion.span layout transition={transition} className="flex items-center justify-center">
        <Waveform handle={audio} variant={isHero ? 'hero' : 'dock'} />
      </motion.span>
    </motion.button>
  )
}

export function SessionScreen() {
  const { micState, toggle } = useMicrophone()
  const audio = useAudioLevel()
  useRealtimeTranscription()
  const phase = useSessionStore((state) => state.phase)
  const connectionState = useSessionStore((state) => state.connectionState)

  // Same end state, no travel: reduced motion collapses every transition to zero rather than
  // routing around the layout animation.
  const prefersReducedMotion = useReducedMotion() === true
  const transition = prefersReducedMotion ? INSTANT : SPRING

  const isSession = phase === 'session'
  const mic = (
    <MicControl
      variant={isSession ? 'dock' : 'hero'}
      micState={micState}
      audio={audio}
      transition={transition}
      onToggle={toggle}
    />
  )

  return (
    <LayoutGroup>
      <main className="relative min-h-dvh overflow-hidden bg-background">
        {isSession && (
          <motion.div
            initial={prefersReducedMotion ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={transition}
            // Left third chat, right two thirds workpane. Below `md` the columns stack, workpane
            // first, rather than squeezing a third of a phone into a conversation.
            className="grid h-dvh grid-cols-1 grid-rows-[1fr_1fr] md:grid-cols-[1fr_2fr] md:grid-rows-1"
          >
            <section className="order-2 flex min-h-0 flex-col gap-3 p-5 md:order-1 md:p-8">
              {/* Bottom-pinned: lines grow upward from the mic and scroll once they run out of room. */}
              <div className="min-h-0 flex-1 overflow-y-auto">
                <div className="flex min-h-full flex-col justify-end">
                  <TranscriptList />
                </div>
              </div>
              {mic}
            </section>
            <Workpane className="order-1 md:order-2" />
          </motion.div>
        )}

        {/*
         * The hero stack stays mounted even in the session phase. Only then can the caption
         * outlive the hero and fade out where it stood while the mic travels away from under it.
         */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-5">
          {!isSession && mic}
          <AnimatePresence initial={false} mode="popLayout">
            {!isSession && (
              <motion.p
                key="caption"
                exit={{ opacity: 0 }}
                transition={transition}
                className="text-neutral-500 text-sm dark:text-neutral-400"
              >
                {captionFor(micState, connectionState)}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </main>
    </LayoutGroup>
  )
}
