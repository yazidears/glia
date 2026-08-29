import type { Candidate } from '@glia/api-client'
import { describe, expect, test } from 'vitest'
import { suggestionsFrom } from '@/components/cala-entity-rail'

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
})
