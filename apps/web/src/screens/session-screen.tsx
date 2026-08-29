import type { ConnectionState } from '@glia/api-client'
import { Mic } from 'lucide-react'
import { useEffect } from 'react'
import { TranscriptList } from '@/components/transcript-list'
import { Waveform } from '@/components/waveform'
import { Workpane } from '@/components/workpane'
import { useAudioLevel } from '@/hooks/use-audio-level'
import { useMicrophone } from '@/hooks/use-microphone'
import { useRealtimeTranscription } from '@/hooks/use-realtime-transcription'
import { cn } from '@/lib/utils'
import { type MicState, useSessionStore } from '@/stores/session'

const CAPTIONS: Record<MicState, string> = {
  idle: 'Start speaking',
  requesting: 'Allow microphone',
  granted: 'Listening',
  denied: 'Try microphone again',
  unsupported: 'Microphone unavailable',
}

function captionFor(micState: MicState, connectionState: ConnectionState): string {
  if (connectionState === 'connecting') {
    return 'Connecting'
  }
  if (connectionState === 'error') {
    return 'Connection interrupted'
  }
  return CAPTIONS[micState]
}

export function SessionScreen() {
  const { micState, toggle } = useMicrophone()
  const audio = useAudioLevel()
  useRealtimeTranscription(audio)
  const phase = useSessionStore((state) => state.phase)
  const connectionState = useSessionStore((state) => state.connectionState)
  const isSession = phase === 'session'
  const isListening = micState === 'granted'
  const caption = captionFor(micState, connectionState)

  useEffect(() => {
    document.title = 'Glia'
  }, [])

  return (
    <main className="session-canvas" data-session={isSession}>
      <a className="glia-wordmark" href="/" aria-label="Glia home">
        glia
      </a>

      <section className="session-hero" data-hidden={isSession} aria-hidden={isSession}>
        <p>Speak until you see it.</p>
        <h1>Speak your mind.</h1>
        <p>Describe the image you can feel but cannot quite prompt.</p>
      </section>

      {isSession ? (
        <div className="session-workspace">
          <section className="transcript-column">
            <div className="transcript-scroll">
              <TranscriptList />
            </div>
          </section>
          <Workpane />
        </div>
      ) : null}

      <button
        type="button"
        onClick={toggle}
        aria-pressed={isListening}
        aria-label={`${caption}. ${isListening ? 'Stop listening' : 'Start listening'}`}
        className={cn('session-mic', isListening && 'is-listening')}
        data-docked={isSession}
      >
        <span className="session-mic-orb">
          <Mic
            aria-hidden="true"
            className={cn(micState === 'requesting' && 'animate-pulse opacity-50')}
            strokeWidth={1.8}
          />
        </span>
        <Waveform active={isListening} handle={audio} variant={isSession ? 'dock' : 'hero'} />
      </button>
    </main>
  )
}
