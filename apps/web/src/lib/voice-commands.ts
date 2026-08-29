export type VoiceCommand = 'generate' | 'select-all'

const COMMAND_PHRASES: ReadonlyArray<readonly [phrase: string, command: VoiceCommand]> = [
  ['selecciona tot', 'select-all'],
  ['selecciona todo', 'select-all'],
  ['select all', 'select-all'],
  ['genera', 'generate'],
  ['generate', 'generate'],
]

export const VOICE_COMMAND_KEYWORDS = ['genera', 'generate', 'selecciona', 'select', 'tot', 'todo']

export function normalizeVoiceCommand(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

export function voiceCommandFor(text: string): VoiceCommand | null {
  const normalized = normalizeVoiceCommand(text)
  return COMMAND_PHRASES.find(([phrase]) => phrase === normalized)?.[1] ?? null
}

/** True while an interim transcript can still become a control utterance. */
export function couldBeVoiceCommand(text: string): boolean {
  const normalized = normalizeVoiceCommand(text)
  return Boolean(normalized) && COMMAND_PHRASES.some(([phrase]) => phrase.startsWith(normalized))
}
