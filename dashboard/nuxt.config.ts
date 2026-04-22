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
        { rel: 'icon', type: 'image/svg+xml', href: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%230d9488'/><path d='M16 8v16M8 16h16' stroke='white' stroke-width='3' stroke-linecap='round'/></svg>" },
      ],
    },
  },

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    oncoteamApiUrl: process.env.NUXT_ONCOTEAM_API_URL || process.env.NUXT_PUBLIC_ONCOTEAM_API_URL || 'https://api.oncoteam.cloud',
    oncoteamApiKey: process.env.NUXT_ONCOTEAM_API_KEY || process.env.NUXT_PUBLIC_ONCOTEAM_API_KEY || '',
    oncofilesReadinessUrl: process.env.NUXT_ONCOFILES_READINESS_URL || 'https://oncofiles.com/readiness',
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
    twilioWebhookUrl: process.env.NUXT_TWILIO_WEBHOOK_URL || '',
    databaseUrl: process.env.DATABASE_URL || '',
  },

  devtools: { enabled: process.dev },

  colorMode: {
    preference: 'light',
  },
})
