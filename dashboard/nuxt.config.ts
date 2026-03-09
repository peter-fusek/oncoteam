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
    detectBrowserLanguage: false,
  },

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    public: {
      oncoteamApiUrl: process.env.NUXT_PUBLIC_ONCOTEAM_API_URL || 'https://oncoteam-production.up.railway.app',
    },
    session: {
      maxAge: 60 * 60 * 24 * 7, // 7 days
    },
    oauth: {
      google: {
        clientId: process.env.NUXT_OAUTH_GOOGLE_CLIENT_ID || '',
        clientSecret: process.env.NUXT_OAUTH_GOOGLE_CLIENT_SECRET || '',
      },
    },
    allowedEmails: process.env.NUXT_ALLOWED_EMAILS || 'peterfusek1980@gmail.com',
    roleMap: process.env.NUXT_ROLE_MAP || '{"peterfusek1980@gmail.com":{"roles":["advocate","patient","doctor"],"phone":"+421903124356"},"peter.fusek@instarea.sk":{"roles":["doctor"],"phone":"+421903124356"},"peter.fusek@instarea.com":{"roles":["doctor"],"phone":"+421903124356"}}',
    twilioAccountSid: process.env.NUXT_TWILIO_ACCOUNT_SID || '',
    twilioAuthToken: process.env.NUXT_TWILIO_AUTH_TOKEN || '',
    twilioWhatsappFrom: process.env.NUXT_TWILIO_WHATSAPP_FROM || '',
    databaseUrl: process.env.DATABASE_URL || '',
  },

  devtools: { enabled: true },

  colorMode: {
    preference: 'dark',
  },
})
