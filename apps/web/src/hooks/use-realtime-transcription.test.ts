import { parseServerMessage } from '@glia/api-client'
import { afterEach, describe, expect, test } from 'vitest'
import { useSessionStore } from '@/stores/session'

describe('live candidate messages', () => {
  afterEach(() => {
    useSessionStore.getState().resetRealtime()
  })

  test('a streamed candidate batch reaches session state instead of leaving demo images active', () => {
    const message = parseServerMessage(
      JSON.stringify({
        type: 'candidates.batch',
        revision: 4,
        candidates: [
          {
            id: 'commons:observatory',
            lane: 'open',
            image_url: 'http://localhost:8000/api/image?url=observatory',
            source_url: 'https://commons.wikimedia.org/wiki/File:Observatory.jpg',
            publisher: 'Wikimedia Commons',
            title: 'Brutalist observatory at night',
            evidence: null,
            licence: 'CC BY-SA 4.0',
            entity_name: null,
            entity_type: null,
            width: 960,
            height: 640,
            score: 0.98,
          },
        ],
      }),
    )

    expect(message?.type).toBe('candidates.batch')
    if (message?.type !== 'candidates.batch') {
      throw new Error('candidate batch did not survive the realtime parser')
    }

    useSessionStore.getState().appendCandidates(message)

    expect(useSessionStore.getState().candidates).toEqual(message.candidates)
    expect(useSessionStore.getState().candidateRevision).toBe(4)
  })

  test('a new subject keeps old photos until its first batch and rejects late old batches', () => {
    const applesIntent = {
      type: 'intent.updated' as const,
      revision: 4,
      transcript: 'Manzanas verdes.',
      intent: {
        subject: 'manzanas verdes',
        moods: [],
        styles: [],
        palette: ['verdes'],
        composition: '',
        medium: '',
        era: '',
      },
      stable: true,
      source: 'pioneer' as const,
      should_discover: true,
      change_reasons: ['initial' as const],
    }
    useSessionStore.getState().setIntent(applesIntent)
    useSessionStore.getState().appendCandidates({
      type: 'candidates.batch',
      revision: 4,
      candidates: [
        {
          id: 'commons:apple',
          lane: 'open',
          image_url: 'http://localhost:8000/api/image?url=apple',
          origin_image_url: 'https://upload.wikimedia.org/apple.jpg',
          source_url: 'https://commons.wikimedia.org/wiki/File:Apple.jpg',
          publisher: 'Wikimedia Commons',
          title: 'Green apple',
          evidence: null,
          licence: 'CC BY-SA 4.0',
          entity_name: null,
          entity_type: null,
          width: 960,
          height: 640,
          score: 0.98,
        },
      ],
    })

    useSessionStore.getState().setIntent({
      ...applesIntent,
      revision: 5,
      transcript: 'Manzanas verdes. Gatos y perros.',
      intent: { ...applesIntent.intent, subject: 'gatos gatos perros', palette: [] },
      change_reasons: ['subject'],
    })

    expect(useSessionStore.getState().candidates[0]?.title).toBe('Green apple')
    expect(useSessionStore.getState().candidateRevision).toBe(4)
    expect(useSessionStore.getState().pendingCandidateRevision).toBe(5)

    useSessionStore.getState().appendCandidates({
      type: 'candidates.batch',
      revision: 5,
      candidates: [],
    })
    expect(useSessionStore.getState().candidates[0]?.title).toBe('Green apple')
    expect(useSessionStore.getState().candidateRevision).toBe(4)
    expect(useSessionStore.getState().pendingCandidateRevision).toBe(5)

    useSessionStore.getState().appendCandidates({
      type: 'candidates.batch',
      revision: 4,
      candidates: [
        {
          id: 'commons:late-apple',
          lane: 'open',
          image_url: 'http://localhost:8000/api/image?url=late-apple',
          origin_image_url: 'https://upload.wikimedia.org/late-apple.jpg',
          source_url: 'https://commons.wikimedia.org/wiki/File:LateApple.jpg',
          publisher: 'Wikimedia Commons',
          title: 'Late apple',
          evidence: null,
          licence: null,
          entity_name: null,
          entity_type: null,
          width: null,
          height: null,
          score: 0.5,
        },
      ],
    })
    expect(useSessionStore.getState().candidates[0]?.title).toBe('Green apple')

    const catsCandidate = {
      id: 'commons:cats-and-dogs',
      lane: 'open' as const,
      image_url: 'http://localhost:8000/api/image?url=cats-and-dogs',
      origin_image_url: 'https://upload.wikimedia.org/cats-and-dogs.jpg',
      source_url: 'https://commons.wikimedia.org/wiki/File:CatsAndDogs.jpg',
      publisher: 'Wikimedia Commons',
      title: 'Cats and dogs',
      evidence: null,
      licence: 'CC BY-SA 4.0',
      entity_name: null,
      entity_type: null,
      width: 960,
      height: 640,
      score: 0.9,
    }
    const catsBatch = {
      type: 'candidates.batch' as const,
      revision: 5,
      candidates: [catsCandidate],
    }
    useSessionStore.getState().appendCandidates(catsBatch)
    expect(useSessionStore.getState().candidates).toEqual(catsBatch.candidates)
    expect(useSessionStore.getState().pendingCandidateRevision).toBeNull()

    const pinnedCat = {
      id: catsCandidate.id,
      title: catsCandidate.title,
      lane: catsCandidate.lane,
      imageUrl: catsCandidate.image_url,
      originImageUrl: catsCandidate.origin_image_url,
      sourceUrl: catsCandidate.source_url,
    }
    useSessionStore.getState().togglePin(pinnedCat)

    useSessionStore.getState().setIntent({
      ...applesIntent,
      revision: 6,
      transcript: 'Manzanas verdes. Gatos y perros.',
      intent: { ...applesIntent.intent, subject: 'los gatos y los perros', palette: [] },
      change_reasons: [],
    })

    expect(useSessionStore.getState().candidates).toEqual(catsBatch.candidates)
    expect(useSessionStore.getState().candidateRevision).toBe(5)
    expect(useSessionStore.getState().pendingCandidateRevision).toBeNull()
    expect(useSessionStore.getState().pinned).toEqual([pinnedCat])
  })
})

describe('OpenAI visual ideas', () => {
  test('structured ideas and keywords survive the realtime parser', () => {
    const message = parseServerMessage(
      JSON.stringify({
        type: 'ideas.updated',
        revision: 5,
        ideas: ['Green apples in a market', 'Macro apple skin', 'Apples in an orchard'],
        keywords: ['green apples', 'orchard'],
        source: 'openai',
      }),
    )

    expect(message?.type).toBe('ideas.updated')
    if (message?.type !== 'ideas.updated') {
      throw new Error('ideas update did not survive the realtime parser')
    }
    expect(message.keywords).toEqual(['green apples', 'orchard'])
  })
})
