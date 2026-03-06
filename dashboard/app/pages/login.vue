<script setup lang="ts">
definePageMeta({ layout: false })

const { loggedIn } = useUserSession()

// If already logged in, redirect to dashboard
if (loggedIn.value) {
  navigateTo('/')
}

// Auto-redirect to Google OAuth (no-click login)
const autoRedirect = ref(true)
onMounted(() => {
  if (!loggedIn.value && autoRedirect.value) {
    setTimeout(() => {
      window.location.href = '/auth/google'
    }, 800)
  }
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-950">
    <div class="text-center space-y-8">
      <!-- Agent character -->
      <div class="relative inline-block">
        <div class="w-24 h-24 mx-auto rounded-2xl bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center shadow-lg shadow-teal-500/20">
          <span class="text-4xl">🧬</span>
        </div>
        <div class="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-green-500 border-2 border-gray-950 animate-pulse" />
      </div>

      <div>
        <h1 class="text-3xl font-bold text-white">Oncoteam</h1>
        <p class="text-gray-400 mt-2">Signing in...</p>
      </div>

      <div class="flex flex-col items-center gap-4">
        <div class="w-6 h-6 border-2 border-teal-500 border-t-transparent rounded-full animate-spin" />
        <UButton
          to="/auth/google"
          external
          icon="i-lucide-log-in"
          size="lg"
          color="white"
          variant="ghost"
          class="px-8"
        >
          Sign in with Google
        </UButton>
      </div>

      <p class="text-xs text-gray-600">Authorized accounts only</p>
    </div>
  </div>
</template>
