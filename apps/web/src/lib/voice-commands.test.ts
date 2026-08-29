import { afterEach, describe, expect, test } from 'vitest'
import { transcriptForGeneration } from '@/hooks/use-generate'
import { visibleCandidateRefs } from '@/lib/pinned-references'
import { couldBeVoiceCommand, voiceCommandFor } from '@/lib/voice-commands'
import { useSessionStore } from '@/stores/session'

describe('spoken controls', () => {
  afterEach(() => useSessionStore.getState().resetRealtime())

  test.each([
    ['G genera.', null],
    ['Genera.', 'generate'],
    ['generate', 'generate'],
    ['Selecciona tot!', 'select-all'],
    ['selecciona todo', 'select-all'],
    ['select all', 'select-all'],
  ])('parses %s as %s', (spoken, expected) => {
    expect(voiceCommandFor(spoken)).toBe(expected)
  })

  test('holds command-shaped interim speech without swallowing an ordinary sentence', () => {
    expect(couldBeVoiceCommand('selecciona')).toBe(true)
    expect(couldBeVoiceCommand('selecciona una foto vermella')).toBe(false)
  })

  test('does not send a control utterance into the generation prompt', () => {
    expect(
      transcriptForGeneration('A blue observatory. Generate.', [
        { itemId: 'idea', text: 'A blue observatory.', complete: true },
        { itemId: 'command', text: 'Generate.', complete: true },
      ]),
    ).toBe('A blue observatory.')
  })

  test('select all adds pins idempotently in visible order', () => {
    const refs = [
      {
        id: 'one',
        title: 'One',
        lane: 'open',
        imageUrl: null,
        originImageUrl: null,
        sourceUrl: null,
      },
      {
        id: 'two',
        title: 'Two',
        lane: 'open',
        imageUrl: null,
        originImageUrl: null,
        sourceUrl: null,
      },
    ]
    useSessionStore.getState().pinMany(refs)
    useSessionStore.getState().pinMany(refs)
    expect(useSessionStore.getState().pinned).toEqual(refs)
  })

  test('select all advances the board to the next unpinned batch', () => {
    const candidates = Array.from({ length: 7 }, (_, index) => ({
      id: `candidate-${index + 1}`,
      lane: 'open' as const,
      image_url: `https://example.com/${index + 1}.jpg`,
      origin_image_url: `https://images.example.com/${index + 1}.jpg`,
      source_url: `https://example.com/source/${index + 1}`,
      publisher: 'Fixture',
      title: `Candidate ${index + 1}`,
      evidence: null,
      licence: null,
      entity_name: null,
      entity_type: null,
      width: 800,
      height: 600,
      score: 1,
    }))
    const firstBatch = visibleCandidateRefs(candidates, [])
    useSessionStore.getState().pinMany(firstBatch)

    expect(firstBatch).toHaveLength(6)
    expect(visibleCandidateRefs(candidates, useSessionStore.getState().pinned)).toEqual([
      expect.objectContaining({ id: 'candidate-7' }),
    ])
  })
})
