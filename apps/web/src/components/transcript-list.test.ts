import { describe, expect, test } from 'vitest'
import { transcriptKeywordTokens } from '@/components/transcript-list'
import { VOICE_COMMAND_KEYWORDS } from '@/lib/voice-commands'

describe('transcript keyword emphasis', () => {
  test('keeps conversational scaffolding grey and marks only active visual keywords', () => {
    const keywords = transcriptKeywordTokens(['manzanas verdes'])
    const words = ['quiero', 'unas', 'manzanas', 'verdes']

    expect(words.map((word) => keywords.has(word))).toEqual([false, false, true, true])
  })

  test('marks spoken controls as active transcript words', () => {
    const keywords = transcriptKeywordTokens(VOICE_COMMAND_KEYWORDS)
    expect(keywords.has('genera')).toBe(true)
    expect(keywords.has('generate')).toBe(true)
    expect(keywords.has('selecciona')).toBe(true)
  })
})
