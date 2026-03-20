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
        <UButton
          to="/auth/google"
          external
          icon="i-lucide-log-in"
          size="lg"
          color="primary"
          variant="solid"
          class="px-8"
        >
          Sign in with Google
        </UButton>
      </div>

      <p class="text-xs text-gray-400">Authorized accounts only</p>
    </div>
  </div>
</template>
