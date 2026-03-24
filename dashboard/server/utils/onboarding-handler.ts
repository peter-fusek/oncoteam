import { getOnboardingState, setOnboardingState } from './onboarding-state'
import type { OnboardingState } from './onboarding-state'

type Lang = 'sk' | 'en'

const ONCOFILES_URL = 'https://aware-kindness-production.up.railway.app'

const SLOVAK_INDICATORS = [
  'ahoj', 'dobry', 'dobrý', 'den', 'deň', 'chcem', 'potrebujem', 'pomoc',
  'prosim', 'prosím', 'dakujem', 'ďakujem', 'zdravim', 'zdravím',
  'halo', 'volam', 'volám', 'mam', 'mám', 'som', 'nie', 'ano', 'áno',
  'liecba', 'liečba', 'rakovina', 'choroba', 'lekar', 'lekár',
]

function detectLanguage(text: string): Lang {
  const lower = text.toLowerCase()
  const words = lower.split(/\s+/)
  for (const word of words) {
    if (SLOVAK_INDICATORS.includes(word)) return 'sk'
  }
  // Check for Slovak diacritics
  if (/[áéíóúýčďĺľňŕšťžäô]/.test(lower)) return 'sk'
  return 'en'
}

function removeDiacritics(text: string): string {
  return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

function generatePatientId(name: string): string {
  return removeDiacritics(name)
    .toLowerCase()
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

const L = (sk: string, en: string) => ({ sk, en })
const t = (msg: { sk: string; en: string }, lang: Lang) => msg[lang]

export interface OnboardingResult {
  type: 'reply' | 'async'
  text?: string
  lang?: Lang
}

export async function handleOnboardingMessage(
  phone: string,
  body: string,
  oncoteamApiUrl: string,
  apiKey: string,
): Promise<OnboardingResult> {
  const state = getOnboardingState(phone)

  if (!state) {
    // Should not happen — caller creates the state before calling this
    return { type: 'reply', text: 'Internal error: no onboarding state.' }
  }

  const lang = state.lang

  switch (state.step) {
    case 'welcome': {
      return handleWelcome(phone, body, state)
    }
    case 'collect_name': {
      return handleCollectName(phone, body, state)
    }
    case 'collect_diagnosis': {
      return handleCollectDiagnosis(phone, body, state)
    }
    case 'collect_language': {
      return handleCollectLanguage(phone, body, state, oncoteamApiUrl, apiKey)
    }
    case 'provisioning': {
      // If we're stuck in provisioning, retry
      return handleCollectLanguage(phone, body, state, oncoteamApiUrl, apiKey)
    }
    case 'oauth_sent': {
      return handleOAuthSent(phone, body, state)
    }
    case 'awaiting_docs': {
      return handleAwaitingDocs(phone, body, state, oncoteamApiUrl, apiKey)
    }
    case 'complete': {
      return handleComplete(state)
    }
    default: {
      return { type: 'reply', text: 'Unknown onboarding state.' }
    }
  }
}

function handleWelcome(phone: string, body: string, state: OnboardingState): OnboardingResult {
  const detectedLang = detectLanguage(body)

  const updatedState: OnboardingState = {
    ...state,
    lang: detectedLang,
    step: 'collect_name',
    updatedAt: Date.now(),
  }
  setOnboardingState(phone, updatedState)

  const text = t(L(
    `Vitajte v Oncoteam! Som AI asistent pre manazment onkologickej liecby.\n\nPomozem vam s:\n- sledovanim labakov a liecby\n- klinickymi studiami\n- denne briefingmi\n\nAko sa vola pacient? (Meno a priezvisko)`,
    `Welcome to Oncoteam! I'm an AI assistant for cancer treatment management.\n\nI can help you with:\n- lab tracking and treatment monitoring\n- clinical trial matching\n- daily briefings\n\nWhat is the patient's name? (First and last name)`,
  ), detectedLang)

  return { type: 'reply', text }
}

function handleCollectName(phone: string, body: string, state: OnboardingState): OnboardingResult {
  const name = body.trim()
  if (name.length < 2 || name.length > 100) {
    return {
      type: 'reply',
      text: t(L(
        'Prosim, zadajte meno a priezvisko pacienta.',
        'Please enter the patient\'s first and last name.',
      ), state.lang),
    }
  }

  const patientId = generatePatientId(name)

  const updatedState: OnboardingState = {
    ...state,
    patientName: name,
    patientId,
    step: 'collect_diagnosis',
    updatedAt: Date.now(),
  }
  setOnboardingState(phone, updatedState)

  const text = t(L(
    `Dakujem. Pacient: *${name}*\n\nAky typ rakoviny/diagnoza? (napr. kolorektálny karcinóm, karcinóm pľúc, karcinóm prsníka...)`,
    `Thank you. Patient: *${name}*\n\nWhat is the cancer type/diagnosis? (e.g. colorectal cancer, lung cancer, breast cancer...)`,
  ), state.lang)

  return { type: 'reply', text }
}

function handleCollectDiagnosis(phone: string, body: string, state: OnboardingState): OnboardingResult {
  const diagnosis = body.trim()
  if (diagnosis.length < 2) {
    return {
      type: 'reply',
      text: t(L(
        'Prosim, zadajte diagnozu/typ rakoviny.',
        'Please enter the diagnosis/cancer type.',
      ), state.lang),
    }
  }

  const updatedState: OnboardingState = {
    ...state,
    diagnosis,
    step: 'collect_language',
    updatedAt: Date.now(),
  }
  setOnboardingState(phone, updatedState)

  const text = t(L(
    `Diagnoza: *${diagnosis}*\n\nV akom jazyku chcete komunikovat?\n\n1. *SK* - Slovensky\n2. *EN* - English`,
    `Diagnosis: *${diagnosis}*\n\nWhat language do you prefer?\n\n1. *SK* - Slovensky\n2. *EN* - English`,
  ), state.lang)

  return { type: 'reply', text }
}

async function handleCollectLanguage(
  phone: string,
  body: string,
  state: OnboardingState,
  oncoteamApiUrl: string,
  apiKey: string,
): Promise<OnboardingResult> {
  const input = body.trim().toLowerCase()

  let chosenLang: Lang = state.lang
  if (['sk', 'slovensky', 'slovenčina', '1'].includes(input)) {
    chosenLang = 'sk'
  }
  else if (['en', 'english', 'anglicky', 'anglictina', '2'].includes(input)) {
    chosenLang = 'en'
  }

  const provisioningState: OnboardingState = {
    ...state,
    lang: chosenLang,
    step: 'provisioning',
    updatedAt: Date.now(),
  }
  setOnboardingState(phone, provisioningState)

  // Call oncoteam backend to provision the patient
  try {
    const headers: Record<string, string> = apiKey
      ? { Authorization: `Bearer ${apiKey}` }
      : {}

    const result = await $fetch<{ bearer_token?: string; patient_id?: string }>(
      `${oncoteamApiUrl}/api/internal/onboard-patient`,
      {
        method: 'POST',
        body: {
          patient_name: state.patientName,
          patient_id: state.patientId,
          diagnosis: state.diagnosis,
          phone,
          lang: chosenLang,
        },
        headers,
      },
    )

    const oauthUrl = `${ONCOFILES_URL}/oauth/authorize/drive?patient_id=${state.patientId}`

    const updatedState: OnboardingState = {
      ...provisioningState,
      bearerToken: result.bearer_token,
      patientId: result.patient_id || state.patientId,
      step: 'oauth_sent',
      updatedAt: Date.now(),
    }
    setOnboardingState(phone, updatedState)

    const text = t(L(
      `Ucet vytvoreny! Jazyk: *${chosenLang.toUpperCase()}*\n\nTeraz prosim prepojte Google Drive kliknutim na tento odkaz:\n\n${oauthUrl}\n\nPo prepojeni napisete *hotovo*.`,
      `Account created! Language: *${chosenLang.toUpperCase()}*\n\nPlease connect your Google Drive by clicking this link:\n\n${oauthUrl}\n\nOnce connected, reply *done*.`,
    ), chosenLang)

    return { type: 'reply', text }
  }
  catch (err) {
    console.error('[onboarding] Provisioning failed:', err)

    // Stay in provisioning step so they can retry
    const text = t(L(
      'Nepodarilo sa vytvorit ucet. Skuste to znova neskor odoslanim akejkolvek spravy.',
      'Failed to create account. Please try again later by sending any message.',
    ), chosenLang)

    return { type: 'reply', text }
  }
}

function handleOAuthSent(phone: string, body: string, state: OnboardingState): OnboardingResult {
  const input = body.trim().toLowerCase()
  const doneWords = ['done', 'hotovo', 'ready', 'pripojene', 'pripojené', 'ok', 'yes', 'ano', 'áno']

  if (doneWords.includes(input)) {
    const updatedState: OnboardingState = {
      ...state,
      step: 'awaiting_docs',
      updatedAt: Date.now(),
    }
    setOnboardingState(phone, updatedState)

    const text = t(L(
      'Super! Teraz nahrajte prve dokumenty do Google Drive priecinka, alebo ich poslite sem ako fotky.\n\nPo nahrati napisete akukolvek spravu.',
      'Great! Now upload your first documents to the Google Drive folder, or send them here as photos.\n\nOnce uploaded, send any message.',
    ), state.lang)

    return { type: 'reply', text }
  }

  // Remind about OAuth
  const oauthUrl = `${ONCOFILES_URL}/oauth/authorize/drive?patient_id=${state.patientId}`
  const text = t(L(
    `Prosim, najskor prepojte Google Drive:\n\n${oauthUrl}\n\nPo prepojeni napisete *hotovo*.`,
    `Please connect Google Drive first:\n\n${oauthUrl}\n\nOnce connected, reply *done*.`,
  ), state.lang)

  return { type: 'reply', text }
}

async function handleAwaitingDocs(
  phone: string,
  body: string,
  state: OnboardingState,
  oncoteamApiUrl: string,
  apiKey: string,
): Promise<OnboardingResult> {
  const updatedState: OnboardingState = {
    ...state,
    step: 'complete',
    updatedAt: Date.now(),
  }
  setOnboardingState(phone, updatedState)

  // Notify admin (fire-and-forget)
  try {
    const headers: Record<string, string> = apiKey
      ? { Authorization: `Bearer ${apiKey}` }
      : {}
    $fetch(`${oncoteamApiUrl}/api/internal/whatsapp-notify`, {
      method: 'POST',
      body: {
        message: `[Onboarding] New patient registered: ${state.patientName} (${state.patientId}), diagnosis: ${state.diagnosis}, phone: ${phone}`,
      },
      headers,
    }).catch(() => {})
  }
  catch {
    // Notification failure must not block
  }

  const text = t(L(
    'Vasa registracia je dokoncena! Administrator aktivuje plny pristup v kratkom case.\n\nDakujeme za registraciu do Oncoteam.',
    'Your setup is complete! An admin will activate your full access shortly.\n\nThank you for registering with Oncoteam.',
  ), state.lang)

  return { type: 'reply', text }
}

function handleComplete(state: OnboardingState): OnboardingResult {
  const text = t(L(
    'Vasa registracia je dokoncena. Administrator aktivuje plny pristup v kratkom case.',
    'Your setup is complete. An admin will activate your full access shortly.',
  ), state.lang)

  return { type: 'reply', text }
}
