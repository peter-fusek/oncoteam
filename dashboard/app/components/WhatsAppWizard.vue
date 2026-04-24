<script setup lang="ts">
import QRCode from 'qrcode'

const { t } = useI18n()
const { waNumber, waLink, waTelLink, completeWizard, skipWizard, track, copyNumber } = useWhatsAppOnboarding()

defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const step = ref(1)
const qrDataUrl = ref('')
const copiedFlash = ref(false)

onMounted(async () => {
  track('wa_promo_viewed', { surface: 'wizard' })
  try {
    qrDataUrl.value = await QRCode.toDataURL(waLink, {
      margin: 1,
      width: 180,
      color: { dark: '#0f172a', light: '#ffffff' },
    })
  } catch {
    qrDataUrl.value = ''
  }
})

function close() {
  emit('update:modelValue', false)
}

function onNext() {
  if (step.value < 3) {
    step.value += 1
    return
  }
  completeWizard()
  close()
}

function onBack() {
  if (step.value > 1) step.value -= 1
}

function onSkip() {
  skipWizard()
  close()
}

async function onSaveContact() {
  track('wa_promo_cta_clicked', { surface: 'wizard', target: 'save-contact' })
  // On mobile this opens the native contact intent; on desktop, just copy
  if (/Mobi|Android|iPhone/.test(navigator.userAgent)) {
    window.location.href = waTelLink
  } else {
    const ok = await copyNumber()
    if (ok) {
      copiedFlash.value = true
      setTimeout(() => (copiedFlash.value = false), 2000)
    }
  }
}

function onOpenChat() {
  track('wa_promo_cta_clicked', { surface: 'wizard', target: 'wa.me' })
  window.open(waLink, '_blank', 'noopener,noreferrer')
}
</script>

<template>
  <div
    v-if="modelValue"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
    role="dialog"
    :aria-label="t('waWizard.dialogLabel', 'WhatsApp onboarding wizard')"
    @click.self="close"
  >
    <div class="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl relative max-h-[90vh] overflow-y-auto">
      <button
        type="button"
        class="absolute top-3 right-3 p-1 text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 rounded"
        :aria-label="t('waWizard.close', 'Close wizard')"
        @click="close"
      >
        <UIcon name="i-lucide-x" class="w-5 h-5" />
      </button>

      <!-- Progress -->
      <div class="flex items-center gap-1 mb-4">
        <div
          v-for="n in 3"
          :key="n"
          class="h-1 flex-1 rounded-full"
          :class="n <= step ? 'bg-emerald-600' : 'bg-gray-200'"
        />
      </div>
      <div class="text-xs text-gray-500 mb-4">
        {{ t('waWizard.stepLabel', 'Step {current} of {total}', { current: step, total: 3 }) }}
      </div>

      <!-- Step 1: Save contact -->
      <div v-if="step === 1">
        <h2 class="text-xl font-bold text-gray-900 mb-2">
          {{ t('waWizard.step1Title', 'Save the number') }}
        </h2>
        <p class="text-sm text-gray-600 mb-4">
          {{ t('waWizard.step1Body', 'Add Oncoteam to your phone contacts so you recognise messages back from the AI.') }}
        </p>
        <div class="rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-3 mb-4">
          <div class="text-xs text-emerald-700 uppercase tracking-wide mb-1">
            {{ t('waWizard.waNumber', 'WhatsApp number') }}
          </div>
          <div class="text-lg font-mono text-gray-900 select-all">{{ waNumber }}</div>
        </div>
        <button
          type="button"
          class="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          @click="onSaveContact"
        >
          <UIcon name="i-lucide-contact-round" class="w-4 h-4" />
          <span v-if="copiedFlash">{{ t('waWizard.copied', 'Copied to clipboard!') }}</span>
          <span v-else>{{ t('waWizard.saveContact', 'Save contact') }}</span>
        </button>
      </div>

      <!-- Step 2: Send first message -->
      <div v-else-if="step === 2">
        <h2 class="text-xl font-bold text-gray-900 mb-2">
          {{ t('waWizard.step2Title', 'Send your first message') }}
        </h2>
        <p class="text-sm text-gray-600 mb-4">
          {{ t('waWizard.step2Body', 'Open WhatsApp and send anything — the first message activates your thread with the AI.') }}
        </p>
        <div class="flex flex-col md:flex-row items-center gap-4 mb-4">
          <img
            v-if="qrDataUrl"
            :src="qrDataUrl"
            :alt="t('waPromo.qrAlt', 'Scan QR to open WhatsApp chat')"
            class="w-40 h-40 rounded border border-gray-200"
          />
          <div class="text-xs text-gray-500 flex-1">
            <div class="font-medium text-gray-700 mb-1">
              {{ t('waWizard.qrTitle', 'Scan with your phone') }}
            </div>
            <p>
              {{ t('waWizard.qrBody', 'Or tap the button below to open WhatsApp directly on this device.') }}
            </p>
          </div>
        </div>
        <button
          type="button"
          class="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          @click="onOpenChat"
        >
          <UIcon name="i-lucide-external-link" class="w-4 h-4" />
          {{ t('waWizard.openChat', 'Open WhatsApp chat') }}
        </button>
      </div>

      <!-- Step 3: Try commands -->
      <div v-else-if="step === 3">
        <h2 class="text-xl font-bold text-gray-900 mb-2">
          {{ t('waWizard.step3Title', 'Try a command or just chat') }}
        </h2>
        <p class="text-sm text-gray-600 mb-4">
          {{ t('waWizard.step3Body', 'Type commands or ask questions in natural language — the AI answers in the same thread.') }}
        </p>
        <div class="space-y-2 mb-4">
          <div class="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2">
            <div class="text-xs font-mono text-emerald-700 mb-0.5">labáky</div>
            <div class="text-xs text-gray-600">{{ t('waWizard.exampleLabs', 'Recent labs + trend highlights') }}</div>
          </div>
          <div class="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2">
            <div class="text-xs font-mono text-emerald-700 mb-0.5">lieky</div>
            <div class="text-xs text-gray-600">{{ t('waWizard.exampleMeds', 'Medication schedule for today') }}</div>
          </div>
          <div class="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2">
            <div class="text-xs font-mono text-emerald-700 mb-0.5">prep</div>
            <div class="text-xs text-gray-600">{{ t('waWizard.examplePrep', 'Pre-cycle safety checklist') }}</div>
          </div>
          <div class="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2">
            <div class="text-xs font-mono text-emerald-700 mb-0.5">
              {{ t('waWizard.exampleFreeCmd', 'Ako je dnes Erika?') }}
            </div>
            <div class="text-xs text-gray-600">{{ t('waWizard.exampleFreeBody', 'Free-text — Claude answers in the same thread') }}</div>
          </div>
        </div>
        <div class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-2">
          <UIcon name="i-lucide-shield-alert" class="w-3.5 h-3.5 inline mr-1" />
          {{ t('waPromo.safetyNotice', 'Only approved phone numbers can message Oncoteam. Contact admin to add family members.') }}
        </div>
      </div>

      <!-- Footer actions -->
      <div class="flex items-center justify-between mt-6 pt-4 border-t border-gray-100">
        <button
          v-if="step > 1"
          type="button"
          class="text-sm text-gray-600 hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 rounded px-2 py-1"
          @click="onBack"
        >
          {{ t('waWizard.back', 'Back') }}
        </button>
        <button
          v-else
          type="button"
          class="text-sm text-gray-500 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 rounded px-2 py-1"
          @click="onSkip"
        >
          {{ t('waWizard.skip', 'Skip') }}
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          @click="onNext"
        >
          {{ step < 3 ? t('waWizard.next', 'Next') : t('waWizard.done', 'Got it') }}
          <UIcon v-if="step < 3" name="i-lucide-arrow-right" class="w-3.5 h-3.5" />
          <UIcon v-else name="i-lucide-check" class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  </div>
</template>
