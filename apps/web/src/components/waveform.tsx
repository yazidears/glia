import { useEffect, useRef } from 'react'
import type { AudioLevelHandle } from '@/hooks/use-audio-level'
import { cn } from '@/lib/utils'
import { useSettings } from '@/stores/settings'

/**
 * Two sizes, one component: the hero card and the docked mic differ only in how many bars fit.
 */
const VARIANTS = {
  hero: { bars: 36, className: 'h-9 w-44' },
  dock: { bars: 24, className: 'h-5 w-24' },
} as const

export type WaveformVariant = keyof typeof VARIANTS

/** Speech sits around 0.05–0.25 RMS after the browser's gain control, so this fills the box. */
const AMPLITUDE_GAIN = 3.2
/** Per-frame approach rate. Low enough to stop the bars strobing, high enough to feel immediate. */
const APPROACH = 0.35

interface WaveformProps {
  handle: AudioLevelHandle
  variant: WaveformVariant
  className?: string
}

function readColor(canvas: HTMLCanvasElement): string {
  // The canvas sets no colour of its own, so this resolves to the inherited `currentColor` and
  // follows the light/dark foreground without the component knowing which one is active.
  return window.getComputedStyle(canvas).color
}

/**
 * A live monochrome level meter, drawn from the analyser's *time domain* data rather than its
 * frequency data. Time domain is the signal itself: it is what proves audio reaches the browser,
 * it responds to loudness symmetrically, and mirroring it around a middle axis is the shape it
 * already has. An FFT would instead show spectral content, which is a different question and
 * looks lopsided because speech energy piles into the lowest bins.
 *
 * The loop never touches React. It reads the analyser, tweens its own bar levels and paints.
 */
function WaveformCanvas({ handle, variant, className }: WaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const { bars: barCount, className: sizeClassName } = VARIANTS[variant]

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) {
      return
    }

    const context = canvas.getContext('2d')
    if (!context) {
      return
    }

    let analyser: AnalyserNode | null = null
    let samples = new Uint8Array(0)
    let color = readColor(canvas)
    let frame: number | null = null
    const levels = new Float32Array(barCount)

    const paint = (): void => {
      // Size the backing store in device pixels so the bars are not soft on a retina display.
      const ratio = window.devicePixelRatio || 1
      const width = Math.max(1, Math.round(canvas.clientWidth * ratio))
      const height = Math.max(1, Math.round(canvas.clientHeight * ratio))
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
      }

      if (analyser) {
        analyser.getByteTimeDomainData(samples)
      }

      const bucket = Math.max(1, Math.floor(samples.length / barCount))
      const slot = width / barCount
      const barWidth = Math.max(ratio, Math.min(slot * 0.5, 3 * ratio))
      const midY = height / 2
      // Silence is a row of dots, never an empty box: the bar can never be shorter than round.
      const restHalf = barWidth / 2
      const maxHalf = Math.max(restHalf, height / 2 - restHalf)

      context.clearRect(0, 0, width, height)
      context.fillStyle = color

      for (let bar = 0; bar < barCount; bar += 1) {
        let target = 0

        if (analyser) {
          const start = bar * bucket
          let sumOfSquares = 0
          for (let offset = 0; offset < bucket; offset += 1) {
            const deviation = ((samples[start + offset] ?? 128) - 128) / 128
            sumOfSquares += deviation * deviation
          }
          target = Math.min(1, Math.sqrt(sumOfSquares / bucket) * AMPLITUDE_GAIN)
        }

        const previous = levels[bar] ?? 0
        const level = previous + (target - previous) * APPROACH
        levels[bar] = level

        const half = Math.max(restHalf, level * maxHalf)
        context.globalAlpha = 0.3 + 0.7 * Math.min(1, level * 2)
        context.beginPath()
        context.roundRect(
          bar * slot + (slot - barWidth) / 2,
          midY - half,
          barWidth,
          half * 2,
          restHalf,
        )
        context.fill()
      }

      context.globalAlpha = 1
    }

    const loop = (): void => {
      paint()
      frame = requestAnimationFrame(loop)
    }

    const stop = (): void => {
      if (frame !== null) {
        cancelAnimationFrame(frame)
        frame = null
      }
    }

    const repaintWhenIdle = (): void => {
      color = readColor(canvas)
      if (frame === null) {
        paint()
      }
    }

    // The loop only runs while there is something to read. Without an analyser one resting frame
    // is painted and nothing spins.
    const unsubscribe = handle.subscribe((next) => {
      analyser = next
      if (next) {
        samples = new Uint8Array(next.fftSize)
        if (frame === null) {
          frame = requestAnimationFrame(loop)
        }
        return
      }
      stop()
      levels.fill(0)
      paint()
    })

    const resizeObserver = new ResizeObserver(repaintWhenIdle)
    resizeObserver.observe(canvas)

    const colorScheme = window.matchMedia('(prefers-color-scheme: dark)')
    colorScheme.addEventListener('change', repaintWhenIdle)

    return () => {
      stop()
      unsubscribe()
      resizeObserver.disconnect()
      colorScheme.removeEventListener('change', repaintWhenIdle)
    }
  }, [handle, barCount])

  return <canvas ref={canvasRef} aria-hidden className={cn('block', sizeClassName, className)} />
}

/**
 * The setting gates a mount rather than a render branch inside the loop, so switching the meter
 * back on gives the canvas a fresh effect instead of a stale one, and switching it off tears the
 * animation frame down rather than leaving it painting into nothing.
 *
 * Nothing around it moves when it goes: the mic button has a fixed width and lays its row out
 * from the orb, so the meter is the only thing that occupies the space it leaves.
 */
export function Waveform(props: WaveformProps) {
  const enabled = useSettings((state) => state.waveform)

  return enabled ? <WaveformCanvas {...props} /> : null
}
