import { EXPECTED_LANGUAGES, type ExpectedLanguage, isExpectedLanguage } from '@glia/api-client'
import { Settings } from 'lucide-react'
import { RadioGroup } from 'radix-ui'
import { type ReactNode, useId } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useCapabilities } from '@/hooks/use-capabilities'
import { isOutputMode, type OutputMode, useSettings } from '@/stores/settings'

/** Endonyms would read better, but every string in this product is English. */
const LANGUAGE_LABELS: Record<ExpectedLanguage, string> = {
  ca: 'Catalan',
  en: 'English',
  es: 'Spanish',
  fr: 'French',
}

const OUTPUT_LABELS: Record<OutputMode, string> = {
  text: 'Text',
  images: 'Images',
  both: 'Both',
}

const OUTPUT_ORDER: readonly OutputMode[] = ['text', 'images', 'both']

const IMAGES_UNAVAILABLE = 'Image discovery not available yet.'
const LEDGER_UNAVAILABLE = 'Credit usage is not available yet.'

interface SettingRowProps {
  label: string
  controlId: string
  control: ReactNode
  hint?: string | undefined
  hintId?: string | undefined
}

function SettingRow({ label, controlId, control, hint, hintId }: SettingRowProps) {
  return (
    <div className="settings-row">
      <div className="settings-row-text">
        <label className="settings-row-label" htmlFor={controlId}>
          {label}
        </label>
        {hint ? (
          <p className="settings-note" id={hintId}>
            {hint}
          </p>
        ) : null}
      </div>
      {control}
    </div>
  )
}

/**
 * Rendered only while the dialog is open — Radix does not mount portal content otherwise — so
 * the capability question is asked once, on first open, and never on the empty opening screen.
 */
function SettingsForm() {
  const output = useSettings((state) => state.output)
  const setOutput = useSettings((state) => state.setOutput)
  const waveform = useSettings((state) => state.waveform)
  const setWaveform = useSettings((state) => state.setWaveform)
  const liveDiscovery = useSettings((state) => state.liveDiscovery)
  const setLiveDiscovery = useSettings((state) => state.setLiveDiscovery)
  const language = useSettings((state) => state.language)
  const setLanguage = useSettings((state) => state.setLanguage)
  const showLedger = useSettings((state) => state.showLedger)
  const setShowLedger = useSettings((state) => state.setShowLedger)

  const { imageDiscovery } = useCapabilities()

  const ids = useId()
  const outputLabelId = `${ids}-output-label`
  const outputNoteId = `${ids}-output-note`
  const ledgerNoteId = `${ids}-ledger-note`
  const waveformId = `${ids}-waveform`
  const discoveryId = `${ids}-discovery`
  const languageId = `${ids}-language`
  const ledgerId = `${ids}-ledger`

  return (
    <div className="settings-body">
      <section className="settings-group">
        <h3 className="settings-group-label" id={outputLabelId}>
          Output
        </h3>
        <RadioGroup.Root
          aria-labelledby={outputLabelId}
          className="settings-segmented"
          onValueChange={(value) => {
            if (isOutputMode(value)) {
              setOutput(value)
            }
          }}
          value={output}
          {...(imageDiscovery ? {} : { 'aria-describedby': outputNoteId })}
        >
          {OUTPUT_ORDER.map((mode) => (
            <RadioGroup.Item
              className="settings-segment"
              disabled={mode !== 'text' && !imageDiscovery}
              key={mode}
              value={mode}
            >
              {OUTPUT_LABELS[mode]}
            </RadioGroup.Item>
          ))}
        </RadioGroup.Root>
        {imageDiscovery ? null : (
          <p className="settings-note" id={outputNoteId}>
            {IMAGES_UNAVAILABLE}
          </p>
        )}
      </section>

      <section className="settings-group">
        <h3 className="settings-group-label">Session</h3>

        <SettingRow
          control={<Switch checked={waveform} id={waveformId} onCheckedChange={setWaveform} />}
          controlId={waveformId}
          label="Waveform"
        />

        <SettingRow
          control={
            <Switch checked={liveDiscovery} id={discoveryId} onCheckedChange={setLiveDiscovery} />
          }
          controlId={discoveryId}
          hint="Off pauses Cala queries."
          label="Live discovery"
        />

        <SettingRow
          control={
            <Select
              onValueChange={(value) => {
                if (isExpectedLanguage(value)) {
                  setLanguage(value)
                }
              }}
              value={language}
            >
              <SelectTrigger className="settings-select" id={languageId}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXPECTED_LANGUAGES.map((code) => (
                  <SelectItem key={code} value={code}>
                    {LANGUAGE_LABELS[code]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
          controlId={languageId}
          label="Language"
        />
      </section>

      <section className="settings-group">
        <h3 className="settings-group-label">Ledger</h3>
        <SettingRow
          control={
            <Switch
              checked={showLedger && imageDiscovery}
              disabled={!imageDiscovery}
              id={ledgerId}
              onCheckedChange={setShowLedger}
              {...(imageDiscovery ? {} : { 'aria-describedby': ledgerNoteId })}
            />
          }
          controlId={ledgerId}
          hint={imageDiscovery ? undefined : LEDGER_UNAVAILABLE}
          hintId={ledgerNoteId}
          label="Show credit usage"
        />
      </section>
    </div>
  )
}

/**
 * The only persistent chrome in the app.
 *
 * It is `position: fixed` and lives outside both phase layouts on purpose: the hero card and the
 * two-column workspace are one shared-element transition, and a control inside either flow would
 * move the microphone. Nothing here costs the empty opening screen a pixel.
 */
export function SettingsDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button aria-label="Settings" className="session-settings" type="button">
          <Settings aria-hidden="true" strokeWidth={1.7} />
        </button>
      </DialogTrigger>
      <DialogContent className="settings-dialog">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>Remembered on this device.</DialogDescription>
        </DialogHeader>
        <SettingsForm />
      </DialogContent>
    </Dialog>
  )
}
