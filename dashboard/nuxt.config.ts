export default defineNuxtConfig({
  compatibilityDate: '2025-05-15',
  future: { compatibilityVersion: 4 },

  modules: ['@nuxt/ui', '@nuxt/eslint', 'nuxt-auth-utils', '@nuxtjs/i18n'],

  i18n: {
    locales: [
      { code: 'en', name: 'English', file: 'en.json' },
      { code: 'sk', name: 'Slovenčina', file: 'sk.json' },
    ],
    defaultLocale: 'sk',
    langDir: '../app/locales',
    lazy: false,
    strategy: 'no_prefix',
    detectBrowserLanguage: {
      useCookie: true,
      cookieKey: 'i18n_locale',
      redirectOn: 'root',
    },
  },

  app: {
    head: {
      link: [
        { rel: 'icon', href: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🩺</text></svg>" },
      ],
    },
  },

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    oncoteamApiUrl: process.env.NUXT_ONCOTEAM_API_URL || process.env.NUXT_PUBLIC_ONCOTEAM_API_URL || 'https://oncoteam-production.up.railway.app',
    oncoteamApiKey: process.env.NUXT_ONCOTEAM_API_KEY || process.env.NUXT_PUBLIC_ONCOTEAM_API_KEY || '',
    public: {},
    session: {
      maxAge: 60 * 60 * 24 * 7, // 7 days
    },
    oauth: {
      google: {
        clientId: process.env.NUXT_OAUTH_GOOGLE_CLIENT_ID || '',
        clientSecret: process.env.NUXT_OAUTH_GOOGLE_CLIENT_SECRET || '',
      },
    },
    allowedEmails: process.env.NUXT_ALLOWED_EMAILS || '',
    roleMap: process.env.NUXT_ROLE_MAP || '{}',
    twilioAccountSid: process.env.NUXT_TWILIO_ACCOUNT_SID || '',
    twilioAuthToken: process.env.NUXT_TWILIO_AUTH_TOKEN || '',
    twilioWhatsappFrom: process.env.NUXT_TWILIO_WHATSAPP_FROM || '',
    databaseUrl: process.env.DATABASE_URL || '',
  },

  devtools: { enabled: process.dev },

  colorMode: {
    preference: 'light',
  },
})
