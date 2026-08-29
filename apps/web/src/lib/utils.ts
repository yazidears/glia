import { type ClassValue, clsx } from 'clsx'
import type { Transition } from 'motion/react'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * The one spring the app moves on. Defined here rather than in the screen that first used it so
 * the workpane's results settle with the same weight as the mic travelling into the dock —
 * two motions that read as one system only if they share a curve.
 */
export const SPRING: Transition = { type: 'spring', stiffness: 240, damping: 28, mass: 0.9 }

/** Reduced motion is the same end state with no travel, not a different arrangement. */
export const INSTANT: Transition = { duration: 0 }
