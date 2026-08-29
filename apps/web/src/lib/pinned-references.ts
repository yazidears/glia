import type { Candidate } from '@glia/api-client'
import type { PinnedRef } from '@/stores/session'

export const IDEA_BOARD_PAGE_SIZE = 6

export interface DemoSticker {
  id: string
  title: string
  lane: 'cited page' | 'open'
  variant: number
}

export const DEMO_STICKERS: readonly DemoSticker[] = [
  { id: 'observatory', title: 'Cobalt observatory', lane: 'cited page', variant: 0 },
  { id: 'brutalist-sun', title: 'Brutalist sun study', lane: 'open', variant: 1 },
  { id: 'quiet-coast', title: 'Quiet Mediterranean', lane: 'open', variant: 2 },
  { id: 'red-editorial', title: 'Red editorial forms', lane: 'cited page', variant: 3 },
  { id: 'night-arch', title: 'Night architecture', lane: 'open', variant: 4 },
  { id: 'blue-type', title: 'Blue type fragment', lane: 'cited page', variant: 5 },
]

export function demoRevealCount(wordCount: number): number {
  return wordCount < 3 ? 0 : Math.min(DEMO_STICKERS.length, Math.ceil((wordCount - 2) / 3) * 2)
}

export function candidateToPinnedRef(candidate: Candidate): PinnedRef {
  return {
    id: candidate.id,
    title: candidate.title ?? candidate.publisher ?? 'Visual reference',
    lane: candidate.lane,
    imageUrl: candidate.image_url,
    sourceUrl: candidate.source_url,
  }
}

export function demoStickerToPinnedRef(sticker: DemoSticker): PinnedRef {
  return {
    id: sticker.id,
    title: sticker.title,
    lane: sticker.lane,
    imageUrl: null,
    sourceUrl: null,
  }
}

export function visibleCandidateRefs(
  candidates: readonly Candidate[],
  pinned: readonly PinnedRef[],
): PinnedRef[] {
  const pinnedIds = new Set(pinned.map((pin) => pin.id))
  return candidates
    .filter((candidate) => !pinnedIds.has(candidate.id))
    .slice(0, IDEA_BOARD_PAGE_SIZE)
    .map(candidateToPinnedRef)
}

export function visibleDemoRefs(pinned: readonly PinnedRef[], revealedCount: number): PinnedRef[] {
  const pinnedIds = new Set(pinned.map((pin) => pin.id))
  return DEMO_STICKERS.filter((sticker) => !pinnedIds.has(sticker.id))
    .slice(0, revealedCount)
    .map(demoStickerToPinnedRef)
}
