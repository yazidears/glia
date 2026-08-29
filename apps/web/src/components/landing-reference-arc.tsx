import { useEffect, useRef, useState } from 'react'
import { CALA_REFERENCE_FIXTURE } from '@/components/reference-data'

const SLOT_COUNT = 8
const SWAP_DURATION = 560

interface LandingReferenceSlot {
  id: string
  referenceIndex: number
  previousReferenceIndex: number | null
  swapId: number
}

interface LandingReferenceArcProps {
  hidden: boolean
}

export function LandingReferenceArc({ hidden }: LandingReferenceArcProps) {
  const [slots, setSlots] = useState<LandingReferenceSlot[]>(() =>
    Array.from({ length: SLOT_COUNT }, (_, index) => ({
      id: `landing-slot-${index + 1}`,
      referenceIndex: index % CALA_REFERENCE_FIXTURE.length,
      previousReferenceIndex: null,
      swapId: 0,
    })),
  )
  const swapTimers = useRef(new Map<string, number>())

  useEffect(() => {
    if (hidden || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      if (hidden) {
        setSlots((current) =>
          current.some((value) => value.previousReferenceIndex !== null)
            ? current.map((value) => ({ ...value, previousReferenceIndex: null }))
            : current,
        )
      }
      return
    }
    let cursor = 0
    let nextReference = SLOT_COUNT
    const interval = window.setInterval(() => {
      const slot = cursor % SLOT_COUNT
      const reference = nextReference % CALA_REFERENCE_FIXTURE.length
      const slotId = `landing-slot-${slot + 1}`
      setSlots((current) =>
        current.map((value, index) =>
          index === slot
            ? {
                ...value,
                previousReferenceIndex: value.referenceIndex,
                referenceIndex: reference,
                swapId: value.swapId + 1,
              }
            : value,
        ),
      )
      const existingTimer = swapTimers.current.get(slotId)
      if (existingTimer !== undefined) {
        window.clearTimeout(existingTimer)
      }
      swapTimers.current.set(
        slotId,
        window.setTimeout(() => {
          setSlots((current) =>
            current.map((value) =>
              value.id === slotId ? { ...value, previousReferenceIndex: null } : value,
            ),
          )
          swapTimers.current.delete(slotId)
        }, SWAP_DURATION),
      )
      cursor += 1
      nextReference += 1
    }, 1_100)

    return () => {
      window.clearInterval(interval)
      for (const timer of swapTimers.current.values()) {
        window.clearTimeout(timer)
      }
      swapTimers.current.clear()
    }
  }, [hidden])

  return (
    <div className="landing-reference-arc" data-hidden={hidden} aria-hidden="true">
      {slots.map((slot, index) => {
        const reference = CALA_REFERENCE_FIXTURE[slot.referenceIndex]
        const previousReference =
          slot.previousReferenceIndex === null
            ? null
            : CALA_REFERENCE_FIXTURE[slot.previousReferenceIndex]
        if (!reference) {
          return null
        }
        return (
          <figure
            className={`landing-reference landing-reference--${index + 1}`}
            data-swapping={previousReference !== null}
            key={slot.id}
          >
            <div className="landing-reference-images" key={`${slot.id}-${slot.swapId}`}>
              {previousReference ? (
                <img
                  alt=""
                  className="landing-reference-image--previous"
                  decoding="async"
                  draggable={false}
                  referrerPolicy="no-referrer"
                  src={previousReference.imageUrl}
                />
              ) : null}
              <img
                alt=""
                className="landing-reference-image--current"
                decoding="async"
                draggable={false}
                loading={index < 6 ? 'eager' : 'lazy'}
                referrerPolicy="no-referrer"
                src={reference.imageUrl}
              />
            </div>
          </figure>
        )
      })}
    </div>
  )
}
