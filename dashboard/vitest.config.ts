import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

/**
 * Minimal Vitest config for dashboard regression tests (#443 Phase F).
 *
 * Scope intentionally tight: pure-JS unit tests for access-control
 * helpers + Nitro event handlers that don't require a full Nuxt runtime.
 * Any test that needs Nuxt's auto-imports / lifecycle belongs in a
 * separate @nuxt/test-utils config, not here.
 */
export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/**/*.test.ts'],
    globals: false,
  },
  resolve: {
    alias: {
      '~': fileURLToPath(new URL('./', import.meta.url)),
      '~~': fileURLToPath(new URL('./', import.meta.url)),
      '#imports': fileURLToPath(new URL('./tests/mocks/nuxt-imports.ts', import.meta.url)),
    },
  },
})
