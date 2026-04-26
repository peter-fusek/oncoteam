<script setup lang="ts">
definePageMeta({ layout: false })

const { loggedIn } = useUserSession()

// If already logged in, redirect to dashboard
if (loggedIn.value) {
  navigateTo('/')
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-[var(--clinical-bg)]">
    <div class="text-center space-y-8">
      <!-- Logo -->
      <div class="relative inline-block">
        <div class="w-24 h-24 mx-auto rounded-2xl bg-gradient-to-br from-teal-600 to-cyan-700 flex items-center justify-center shadow-lg shadow-teal-600/15">
          <span class="text-4xl text-white">+</span>
        </div>
        <div class="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-emerald-500 border-2 border-[var(--clinical-bg)] flex items-center justify-center">
          <span class="text-white text-[8px]">&#10003;</span>
        </div>
      </div>

      <div>
        <h1 class="text-3xl font-bold text-gray-900 font-display">Oncoteam</h1>
        <p class="text-gray-500 mt-2">Sign in to continue</p>
      </div>

      <div class="flex flex-col items-center gap-4">
        <!-- Plain <a> on purpose: NuxtLink/UButton with external=true was being -->
        <!-- classified as a popup by Chrome's blocker on some setups. A bare anchor -->
        <!-- with same-origin href guarantees a normal top-level navigation. -->
        <a
          href="/auth/google"
          class="inline-flex items-center gap-2 px-8 py-3 rounded-lg bg-teal-600 hover:bg-teal-700 text-white font-medium text-base shadow-sm transition-colors"
        >
          <span class="i-lucide-log-in w-5 h-5" aria-hidden="true" />
          Sign in with Google
        </a>
      </div>

      <p class="text-xs text-gray-400">Authorized accounts only</p>

      <div class="pt-4 border-t border-gray-200">
        <NuxtLink to="/demo" class="text-sm text-teal-600 hover:text-teal-700 hover:underline">
          Or try the live demo &rarr;
        </NuxtLink>
      </div>
    </div>
  </div>
</template>
