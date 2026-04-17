/**
 * WhatsApp onboarding promo — per-user dismissal + first-login wizard trigger.
 *
 * Storage layout (localStorage):
 * - `oncoteam:wa-onboarded`       — wizard completed or skipped (persists forever)
 * - `oncoteam:wa-promo-dismissed` — banner dismissed (re-surfaces after 30 days)
 *
 * Telemetry events are console-logged under `[wa-promo]` so they're captured
 * by existing analytics pipelines without a dedicated backend endpoint yet.
 * When issue #382 adds structured audit log, switch to that.
 */

const WA_NUMBER = '+421 800 223 213'
const WA_NUMBER_RAW = '421800223213'
const WA_DEEPLINK_TEXT = 'Ahoj%20Oncoteam'

const STORAGE_KEY_ONBOARDED = 'oncoteam:wa-onboarded'
const STORAGE_KEY_DISMISSED = 'oncoteam:wa-promo-dismissed'
const DISMISS_TTL_MS = 30 * 24 * 60 * 60 * 1000 // 30 days

type TelemetryEvent = 'wa_promo_viewed' | 'wa_promo_cta_clicked' | 'wa_promo_dismissed' | 'wa_wizard_completed' | 'wa_wizard_skipped'

export function useWhatsAppOnboarding() {
  const waNumber = WA_NUMBER
  const waNumberRaw = WA_NUMBER_RAW
  const waLink = `https://wa.me/${WA_NUMBER_RAW}?text=${WA_DEEPLINK_TEXT}`
  const waTelLink = `tel:${WA_NUMBER_RAW}`

  const onboarded = useState('wa-onboarded', () => false)
  const dismissed = useState('wa-promo-dismissed', () => false)

  function readFlags() {
    if (!import.meta.client) return
    try {
      onboarded.value = localStorage.getItem(STORAGE_KEY_ONBOARDED) === 'true'
      const raw = localStorage.getItem(STORAGE_KEY_DISMISSED)
      if (raw) {
        const ts = parseInt(raw, 10)
        if (!isNaN(ts) && Date.now() - ts < DISMISS_TTL_MS) {
          dismissed.value = true
        } else {
          localStorage.removeItem(STORAGE_KEY_DISMISSED)
          dismissed.value = false
        }
      }
    } catch {
      // localStorage disabled / private mode — treat as first-time user
    }
  }

  function dismissPromo() {
    if (!import.meta.client) return
    try {
      localStorage.setItem(STORAGE_KEY_DISMISSED, String(Date.now()))
    } catch {
      // noop
    }
    dismissed.value = true
    track('wa_promo_dismissed')
  }

  function completeWizard() {
    if (!import.meta.client) return
    try {
      localStorage.setItem(STORAGE_KEY_ONBOARDED, 'true')
    } catch {
      // noop
    }
    onboarded.value = true
    track('wa_wizard_completed')
  }

  function skipWizard() {
    if (!import.meta.client) return
    try {
      localStorage.setItem(STORAGE_KEY_ONBOARDED, 'true')
    } catch {
      // noop
    }
    onboarded.value = true
    track('wa_wizard_skipped')
  }

  function track(event: TelemetryEvent, meta?: Record<string, unknown>) {
    if (!import.meta.client) return
    try {
      // eslint-disable-next-line no-console
      console.info(`[wa-promo] ${event}`, meta ?? {})
    } catch {
      // noop
    }
  }

  /**
   * Copy the WA number to clipboard. Used as a desktop fallback when
   * the tel: / wa.me intents don't trigger a contact-save UI.
   */
  async function copyNumber(): Promise<boolean> {
    if (!import.meta.client) return false
    try {
      await navigator.clipboard.writeText(WA_NUMBER)
      return true
    } catch {
      return false
    }
  }

  return {
    waNumber,
    waNumberRaw,
    waLink,
    waTelLink,
    onboarded: readonly(onboarded),
    dismissed: readonly(dismissed),
    readFlags,
    dismissPromo,
    completeWizard,
    skipWizard,
    track,
    copyNumber,
  }
}
