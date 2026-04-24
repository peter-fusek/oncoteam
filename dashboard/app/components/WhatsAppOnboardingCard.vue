<script setup lang="ts">
import QRCode from 'qrcode'

const { t } = useI18n()
const {
  waNumber,
  waLink,
  dismissed,
  onboarded,
  readFlags,
  dismissPromo,
  track,
  copyNumber,
} = useWhatsAppOnboarding()

const qrDataUrl = ref<string>('')
const expanded = ref(false)
const copiedFlash = ref(false)

const emit = defineEmits<{
  (e: 'open-wizard'): void
}>()

onMounted(async () => {
  readFlags()
  if (!dismissed.value) {
    track('wa_promo_viewed')
  }
  try {
    qrDataUrl.value = await QRCode.toDataURL(waLink, {
      margin: 1,
      width: 160,
      color: { dark: '#0f172a', light: '#ffffff' },
    })
  } catch {
    qrDataUrl.value = ''
  }
})

function onOpenChat() {
  track('wa_promo_cta_clicked', { target: 'wa.me' })
  window.open(waLink, '_blank', 'noopener,noreferrer')
}

async function onSaveContact() {
  track('wa_promo_cta_clicked', { target: 'save-contact' })
  const ok = await copyNumber()
  if (ok) {
    copiedFlash.value = true
    setTimeout(() => (copiedFlash.value = false), 2000)
  }
}

function onOpenWizard() {
  track('wa_promo_cta_clicked', { target: 'wizard' })
  emit('open-wizard')
}

const show = computed(() => !dismissed.value)
</script>

<template>
  <div
    v-if="show"
    class="rounded-xl border border-emerald-200 bg-gradient-to-br from-emerald-50 via-white to-teal-50 p-4 shadow-sm relative overflow-hidden"
    role="region"
    :aria-label="t('waPromo.regionLabel', 'WhatsApp onboarding')"
  >
    <!-- Dismiss -->
    <button
      type="button"
      class="absolute top-2 right-2 p-1 text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 rounded"
      :aria-label="t('waPromo.dismiss', 'Dismiss WhatsApp promo')"
      @click="dismissPromo"
    >
      <UIcon name="i-lucide-x" class="w-4 h-4" />
    </button>

    <div class="flex flex-col md:flex-row items-start gap-4">
      <!-- Icon + heading -->
      <div class="flex items-start gap-3 flex-1">
        <div class="rounded-full bg-emerald-100 p-2 shrink-0">
          <UIcon name="i-lucide-message-circle" class="w-5 h-5 text-emerald-700" />
        </div>
        <div class="flex-1 min-w-0">
          <h3 class="text-sm font-semibold text-gray-900">
            {{ t('waPromo.title', 'Message Oncoteam on WhatsApp') }}
          </h3>
          <p class="text-xs text-gray-600 mt-1">
            {{ t('waPromo.tagline', 'Discreet. Voice notes. Works from any phone.') }}
          </p>
          <div class="mt-2 inline-flex items-center gap-2 rounded-lg bg-white border border-emerald-200 px-3 py-1.5">
            <UIcon name="i-lucide-phone" class="w-3.5 h-3.5 text-emerald-700" />
            <span class="text-sm font-mono text-gray-900 select-all">{{ waNumber }}</span>
          </div>
        </div>
      </div>

      <!-- QR code (desktop only, mobile uses save-contact CTA) -->
      <div v-if="qrDataUrl" class="hidden md:block shrink-0">
        <img
          :src="qrDataUrl"
          :alt="t('waPromo.qrAlt', 'Scan to open WhatsApp chat with Oncoteam')"
          class="w-20 h-20 rounded border border-gray-200"
        />
        <div class="text-[10px] text-center text-gray-500 mt-1">
          {{ t('waPromo.qrHint', 'Scan with phone') }}
        </div>
      </div>
    </div>

    <!-- CTAs -->
    <div class="flex flex-wrap gap-2 mt-3">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        @click="onOpenChat"
      >
        <UIcon name="i-lucide-external-link" class="w-3.5 h-3.5" />
        {{ t('waPromo.openChat', 'Open chat') }}
      </button>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg bg-white border border-gray-300 hover:border-gray-400 text-gray-700 text-xs font-medium px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        @click="onSaveContact"
      >
        <UIcon name="i-lucide-contact-round" class="w-3.5 h-3.5" />
        <span v-if="copiedFlash">{{ t('waPromo.copied', 'Copied!') }}</span>
        <span v-else>{{ t('waPromo.saveContact', 'Save contact') }}</span>
      </button>
      <button
        v-if="!onboarded"
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg bg-white border border-gray-300 hover:border-gray-400 text-gray-700 text-xs font-medium px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        @click="onOpenWizard"
      >
        <UIcon name="i-lucide-sparkles" class="w-3.5 h-3.5 text-amber-500" />
        {{ t('waPromo.howItWorks', '3-step guide') }}
      </button>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg text-gray-600 hover:text-gray-900 text-xs font-medium px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? t('waPromo.hideExamples', 'Hide examples') : t('waPromo.showExamples', 'See examples') }}
        <UIcon :name="expanded ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'" class="w-3.5 h-3.5" />
      </button>
    </div>

    <!-- Expanded examples -->
    <div v-if="expanded" class="mt-3 pt-3 border-t border-emerald-100 space-y-2">
      <div class="text-xs text-gray-500 font-medium uppercase tracking-wide">
        {{ t('waPromo.examplesTitle', 'Example messages') }}
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
        <div class="rounded-lg bg-white border border-gray-200 px-3 py-2">
          <div class="text-xs font-mono text-emerald-700 mb-1">labáky</div>
          <div class="text-[11px] text-gray-600 leading-tight">
            {{ t('waPromo.example1', 'Recent hematology values · ANC, PLT, HGB trends') }}
          </div>
        </div>
        <div class="rounded-lg bg-white border border-gray-200 px-3 py-2">
          <div class="text-xs font-mono text-emerald-700 mb-1">
            {{ t('waPromo.example2Cmd', 'Ako je dnes Erika?') }}
          </div>
          <div class="text-[11px] text-gray-600 leading-tight">
            {{ t('waPromo.example2', 'Free-text chat — Claude answers in the same thread') }}
          </div>
        </div>
        <div class="rounded-lg bg-white border border-gray-200 px-3 py-2">
          <div class="text-xs font-mono text-emerald-700 mb-1">
            🎙️ {{ t('waPromo.example3Cmd', 'voice note') }}
          </div>
          <div class="text-[11px] text-gray-600 leading-tight">
            {{ t('waPromo.example3', 'Whisper transcription + briefing response') }}
          </div>
        </div>
      </div>
      <div class="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-2">
        <UIcon name="i-lucide-shield-alert" class="w-3.5 h-3.5 inline mr-1" />
        {{ t('waPromo.safetyNotice', 'Only approved phone numbers can message Oncoteam. Contact the administrator to add family members.') }}
      </div>
    </div>
  </div>
</template>
