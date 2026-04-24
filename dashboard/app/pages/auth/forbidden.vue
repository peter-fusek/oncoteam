<script setup lang="ts">
/**
 * #443 Phase E — dedicated "no patient access" landing page.
 *
 * Reached when:
 * - google.get.ts OAuth callback resolves an email with no NUXT_ROLE_MAP
 *   entry (or one whose entry declares no patient scope)
 * - session-patch.ts detects an existing session whose email lost its
 *   role-map entry mid-session
 *
 * Exists because the prior behavior (throw 403 / redirect silently to
 * /login) gave users no clue WHY they couldn't get in. A physician or
 * partner onboarding without a role-map entry would loop at /login,
 * confused; this page tells them who to contact.
 */
definePageMeta({ layout: false })

const route = useRoute()
const email = (route.query.email as string) || ''
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-[var(--clinical-bg)]">
    <div class="text-center space-y-6 max-w-md px-6">
      <!-- Lock icon -->
      <div class="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-lg shadow-amber-600/15">
        <UIcon name="i-lucide-lock" class="text-white text-4xl" />
      </div>

      <div>
        <h1 class="text-2xl font-bold text-gray-900 font-display">
          No patient access
        </h1>
        <p class="text-gray-600 mt-3 leading-relaxed">
          Your Google account isn't configured for any patient in Oncoteam.
          This usually means you haven't been onboarded yet, or your access
          was revoked.
        </p>
        <p v-if="email" class="text-sm text-gray-500 mt-2">
          Signed-in email: <span class="font-mono">{{ email }}</span>
        </p>
      </div>

      <div class="bg-white rounded-xl border border-gray-200 p-5 text-left space-y-3">
        <h2 class="text-sm font-semibold text-gray-900">
          What to do next
        </h2>
        <ul class="text-sm text-gray-600 space-y-2 list-disc list-inside">
          <li>If you should have access, ask your Oncoteam administrator to add your email to the role map.</li>
          <li>If you're exploring the product, use the <NuxtLink to="/demo" class="text-teal-600 hover:underline">live demo</NuxtLink> instead.</li>
          <li>If this is a mistake, try signing in with a different Google account.</li>
        </ul>
      </div>

      <div class="flex items-center justify-center gap-4 pt-2">
        <NuxtLink
          to="/login"
          class="text-sm text-teal-600 hover:text-teal-700 hover:underline"
        >
          &larr; Back to sign-in
        </NuxtLink>
        <NuxtLink
          to="/demo"
          class="text-sm text-gray-500 hover:text-gray-700 hover:underline"
        >
          Try the demo
        </NuxtLink>
      </div>
    </div>
  </div>
</template>
