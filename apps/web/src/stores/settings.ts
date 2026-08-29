import {
  DEFAULT_EXPECTED_LANGUAGE,
  type ExpectedLanguage,
  isExpectedLanguage,
} from '@glia/api-client'
import { create } from 'zustand'
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware'

/**
 * What the user wants back from a session. The image lanes are live, so `images` is a real
 * mode rather than a promise — `/health` still reports whether this server can honour it,
 * and a server with every lane down is the one case where images cannot arrive.
 */
export type OutputMode = 'text' | 'images' | 'both'

const OUTPUT_MODES: readonly OutputMode[] = ['text', 'images', 'both']

export function isOutputMode(value: unknown): value is OutputMode {
  return OUTPUT_MODES.includes(value as OutputMode)
}

/**
 * The persisted half. Kept apart from the actions so `partialize` is a type, not a guess, and
 * apart from the session store entirely: settings outlive a session, session state does not.
 */
export interface SettingsValues {
  output: OutputMode
  waveform: boolean
  liveDiscovery: boolean
  language: ExpectedLanguage
  showLedger: boolean
}

interface SettingsActions {
  setOutput: (output: OutputMode) => void
  setWaveform: (waveform: boolean) => void
  setLiveDiscovery: (liveDiscovery: boolean) => void
  setLanguage: (language: ExpectedLanguage) => void
  setShowLedger: (showLedger: boolean) => void
}

export type SettingsState = SettingsValues & SettingsActions

export const DEFAULT_SETTINGS: SettingsValues = {
  // The grid is the product. Both open-corpus lanes answer in well under a second, so the
  // default that used to promise nothing now promises what the app actually does.
  output: 'images',
  waveform: true,
  liveDiscovery: true,
  language: DEFAULT_EXPECTED_LANGUAGE,
  showLedger: false,
}

/**
 * One versioned key. Bumping the suffix retires a shape rather than migrating it.
 *
 * v2 exists for exactly one reason: `output` defaulted to `text` while the image lanes were
 * dead, and everyone who opened the app in that window has `text` written into their
 * `localStorage`. Migrating the value would be guessing at a preference nobody expressed;
 * retiring the key hands them the new default and lets them choose again.
 */
const STORAGE_KEY = 'glia:settings:v2'

/**
 * `localStorage` is not a given: a private window, blocked site data or a storage quota all throw
 * on plain property access, and an uncaught throw here happens during the store's first read —
 * before anything renders. The fallback keeps the choice alive for the tab and lets the next
 * reload start from defaults, which is the honest outcome when the browser refuses to remember.
 */
function createGuardedStorage(): StateStorage {
  const fallback = new Map<string, string>()

  return {
    getItem: (name) => {
      try {
        return window.localStorage.getItem(name)
      } catch {
        return fallback.get(name) ?? null
      }
    },
    setItem: (name, value) => {
      try {
        window.localStorage.setItem(name, value)
      } catch {
        fallback.set(name, value)
      }
    },
    removeItem: (name) => {
      try {
        window.localStorage.removeItem(name)
      } catch {
        fallback.delete(name)
      }
    },
  }
}

/**
 * Anything that has been through `localStorage` is external data: another tab, an older build or
 * a hand-edited value can all put a shape in there that this build never wrote. Every field is
 * checked, and a field that fails falls back to its default rather than to `undefined`.
 */
function sanitize(persisted: unknown): Partial<SettingsValues> {
  if (typeof persisted !== 'object' || persisted === null || Array.isArray(persisted)) {
    return {}
  }
  const candidate = persisted as Record<string, unknown>
  const values: Partial<SettingsValues> = {}

  if (isOutputMode(candidate.output)) {
    values.output = candidate.output
  }
  if (typeof candidate.waveform === 'boolean') {
    values.waveform = candidate.waveform
  }
  if (typeof candidate.liveDiscovery === 'boolean') {
    values.liveDiscovery = candidate.liveDiscovery
  }
  if (isExpectedLanguage(candidate.language)) {
    values.language = candidate.language
  }
  if (typeof candidate.showLedger === 'boolean') {
    values.showLedger = candidate.showLedger
  }

  return values
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      ...DEFAULT_SETTINGS,
      setOutput: (output) => set({ output }),
      setWaveform: (waveform) => set({ waveform }),
      setLiveDiscovery: (liveDiscovery) => set({ liveDiscovery }),
      setLanguage: (language) => set({ language }),
      setShowLedger: (showLedger) => set({ showLedger }),
    }),
    {
      name: STORAGE_KEY,
      version: 2,
      storage: createJSONStorage(createGuardedStorage),
      partialize: ({ output, waveform, liveDiscovery, language, showLedger }): SettingsValues => ({
        output,
        waveform,
        liveDiscovery,
        language,
        showLedger,
      }),
      merge: (persisted, current) => ({ ...current, ...sanitize(persisted) }),
    },
  ),
)
