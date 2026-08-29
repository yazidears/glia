import type { Candidate } from '@glia/api-client'
import { describe, expect, test } from 'vitest'
import { entityRailContent, suggestionsFrom } from '@/components/cala-entity-rail'

function candidate(overrides: Partial<Candidate>): Candidate {
  return {
    id: 'candidate',
    lane: 'cited',
    image_url: 'https://publisher.example/image.jpg',
    origin_image_url: 'https://publisher.example/image.jpg',
    source_url: 'https://publisher.example/story',
    publisher: 'Publisher',
    title: 'Story',
    evidence: null,
    licence: null,
    entity_name: null,
    entity_type: null,
    width: null,
    height: null,
    score: 1,
    ...overrides,
  }
}

describe('Cala entity rail', () => {
  test('keeps distinct cited entities and ignores open-lane metadata', () => {
    const suggestions = suggestionsFrom([
      candidate({ entity_name: 'Braun', entity_type: 'Company' }),
      candidate({ id: 'duplicate', entity_name: 'Braun', entity_type: 'Company' }),
      candidate({
        id: 'open',
        lane: 'open',
        entity_name: 'Unverified brand',
        entity_type: 'Company',
      }),
      candidate({ id: 'product', entity_name: 'T3 radio', entity_type: 'Product' }),
    ])

    expect(suggestions).toEqual([
      { name: 'Braun', type: 'Company' },
      { name: 'T3 radio', type: 'Product' },
    ])
  })

  test('the static preview yields as soon as realtime intent arrives', () => {
    const intentUpdate = {
      type: 'intent.updated' as const,
      revision: 4,
      transcript: 'A premium informal clothing brand',
      intent: {
        subject: 'clothing brand',
        moods: ['informal'],
        styles: ['premium editorial'],
        palette: [],
        composition: '',
        medium: 'photograph',
        era: '',
      },
      stable: false,
      source: 'local' as const,
      should_discover: false,
      change_reasons: [],
    }

    expect(
      entityRailContent({
        candidates: [],
        ideasUpdate: null,
        intentUpdate,
        hasTranscript: true,
        previewSuggestions: [{ name: 'Braun', type: 'Company' }],
      }),
    ).toEqual({
      label: 'Listening · direction',
      source: 'intent',
      suggestions: [
        { name: 'clothing brand', type: 'Subject' },
        { name: 'premium editorial', type: 'Style' },
        { name: 'photograph', type: 'Medium' },
      ],
    })
  })

  test('settled ideas yield to cited Cala entities when they arrive', () => {
    const base = {
      candidates: [] as Candidate[],
      intentUpdate: null,
      hasTranscript: true,
      previewSuggestions: [{ name: 'Braun', type: 'Company' }],
    }
    const ideasUpdate = {
      type: 'ideas.updated' as const,
      revision: 5,
      ideas: ['Quiet tailoring', 'Editorial fabric study'],
      keywords: ['tailoring'],
      source: 'openai' as const,
    }

    expect(entityRailContent({ ...base, ideasUpdate })?.source).toBe('ideas')
    expect(
      entityRailContent({
        ...base,
        ideasUpdate,
        candidates: [candidate({ entity_name: 'Lemaire', entity_type: 'Company' })],
      }),
    ).toEqual({
      label: 'Cala · related',
      source: 'cala',
      suggestions: [{ name: 'Lemaire', type: 'Company' }],
    })
  })
})
