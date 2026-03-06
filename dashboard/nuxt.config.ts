export default defineNuxtConfig({
  compatibilityDate: '2025-05-15',
  future: { compatibilityVersion: 4 },

  modules: ['@nuxt/ui', '@nuxt/eslint'],

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    public: {
      oncoteamApiUrl: process.env.NUXT_PUBLIC_ONCOTEAM_API_URL || 'https://oncoteam-production.up.railway.app',
    },
    databaseUrl: process.env.DATABASE_URL || '',
  },

  devtools: { enabled: true },

  colorMode: {
    preference: 'dark',
  },
})
